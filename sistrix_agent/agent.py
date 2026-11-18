from __future__ import annotations

from datetime import datetime, timezone

from .analysis import build_competitor_report, danger_score, is_branch_relevant, is_excluded, lost_keywords
from .client import SistrixClient
from .config import Config
from .models import AnalysisResult, DomainProfile


async def collect_profile(client: SistrixClient, domain: str, cfg: Config, own: bool = False) -> DomainProfile:
    visindex = await client.visindex(domain, cfg.country)
    kwcount = await client.kwcount(domain, cfg.country)
    kwcount_top10 = await client.kwcount_top10(domain, cfg.country)
    regex = None if own else cfg.branch_regex
    row_cap = max(1, cfg.max_keywords_per_domain)
    keywords = await client.domain_keywords(
        domain,
        cfg.country,
        to_pos=cfg.max_pos,
        regex_keyword=regex,
        page_size=min(cfg.page_size, row_cap),
        max_pages=1 if row_cap < cfg.page_size else cfg.max_pages,
    )
    keywords = keywords[:row_cap]
    keywords.sort(key=lambda k: (k.position, k.keyword))
    top_keywords = [k.keyword for k in keywords if k.position <= 10][:12]
    return DomainProfile(
        domain=domain,
        visindex=visindex,
        kwcount=kwcount,
        kwcount_top10=kwcount_top10,
        keywords=keywords,
        top_keywords=top_keywords,
    )


async def probe_candidate(client: SistrixClient, domain: str, cfg: Config) -> DomainProfile:
    visindex = await client.visindex(domain, cfg.country)
    kwcount_top10 = await client.kwcount_top10(domain, cfg.country)
    probe_rows = await client.domain_keywords(
        domain,
        cfg.country,
        to_pos=10,
        regex_keyword=cfg.branch_regex,
        page_size=cfg.candidate_keyword_probe,
        max_pages=1,
    )
    probe_rows.sort(key=lambda k: (k.position, k.keyword))
    return DomainProfile(
        domain=domain,
        visindex=visindex,
        kwcount_top10=kwcount_top10,
        keywords=probe_rows,
        top_keywords=[k.keyword for k in probe_rows][:12],
    )


async def run_weekly_analysis(client: SistrixClient, cfg: Config) -> AnalysisResult:
    own = await collect_profile(client, cfg.own_domain, cfg, own=True)
    candidate_domains = await client.competitors(cfg.own_domain, cfg.country, cfg.competitor_list_limit)
    own_normalized = cfg.own_domain.lower().removeprefix("www.")
    probes: list[DomainProfile] = []
    for domain in candidate_domains:
        normalized = domain.lower().removeprefix("www.")
        if normalized == own_normalized or is_excluded(domain, cfg):
            continue
        probe = await probe_candidate(client, domain, cfg)
        if is_branch_relevant(probe, cfg):
            probes.append(probe)
    scored = []
    for probe in probes:
        lost, overlap = lost_keywords(own, probe, cfg)
        scored.append((danger_score(probe, own, lost, overlap), probe))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    chosen = [probe for _, probe in scored[: cfg.top_competitors]]
    full_profiles = [await collect_profile(client, p.domain, cfg, own=False) for p in chosen]
    reports = []
    for profile in full_profiles:
        base_lost, _ = lost_keywords(own, profile, cfg)
        candidates = [item.keyword for item in base_lost[: cfg.search_volume_lookup_limit]]
        volumes = await client.search_volumes(candidates, cfg.country) if candidates else {}
        reports.append(build_competitor_report(own, profile, cfg, volumes=volumes))
    reports.sort(key=lambda r: danger_score(r.profile, own, r.lost, r.overlap), reverse=True)
    return AnalysisResult(
        company_name=cfg.company_name,
        own_domain=cfg.own_domain,
        country=cfg.country,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        own=own,
        competitors=reports[: cfg.top_competitors],
    )
