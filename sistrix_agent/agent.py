from __future__ import annotations

from datetime import datetime, timezone

from .analysis import is_excluded, select_top_competitors
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


async def run_weekly_analysis(client: SistrixClient, cfg: Config) -> AnalysisResult:
    own = await collect_profile(client, cfg.own_domain, cfg, own=True)
    candidate_domains = await client.competitors(cfg.own_domain, cfg.country, cfg.competitor_list_limit)
    candidates: list[DomainProfile] = []
    for domain in candidate_domains:
        normalized = domain.lower().removeprefix("www.")
        if normalized == cfg.own_domain.lower().removeprefix("www."):
            continue
        if is_excluded(domain, cfg):
            continue
        candidates.append(await collect_profile(client, domain, cfg, own=False))
    competitors = select_top_competitors(own, candidates, cfg)
    return AnalysisResult(
        company_name=cfg.company_name,
        own_domain=cfg.own_domain,
        country=cfg.country,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        own=own,
        competitors=competitors,
    )
