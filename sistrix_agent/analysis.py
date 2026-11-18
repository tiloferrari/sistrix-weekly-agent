from __future__ import annotations

import re

from .config import Config
from .models import CompetitorReport, DomainProfile, KeywordRank, LostKeyword


def _normalize(domain: str) -> str:
    return domain.lower().removeprefix("www.")


def is_excluded(domain: str, cfg: Config) -> bool:
    normalized = _normalize(domain)
    return any(normalized == d or normalized.endswith("." + d) for d in cfg.excluded_domains)


def is_same_party(domain: str, own_domain: str) -> bool:
    normalized = _normalize(domain)
    own = _normalize(own_domain)
    return normalized == own or normalized.endswith("." + own) or own.endswith("." + normalized)


def is_branch_relevant(profile: DomainProfile, cfg: Config) -> bool:
    if is_excluded(profile.domain, cfg):
        return False
    text = f"{profile.domain} {' '.join(profile.top_keywords)}"
    return bool(re.search(cfg.branch_regex, text))


def classify_business(profile: DomainProfile, cfg: Config) -> str:
    text = f"{profile.domain} {' '.join(profile.top_keywords)}".lower()
    if re.search(r"interim", text):
        return "Interim-Management-Provider"
    if re.search(r"(personalberatung|personalvermittl|personalvermittler|recruiting|headhunt|personaldienstl|zeitarbeit)", text):
        return "Personalberatung / Personalvermittler"
    if re.search(r"(portal|plattform|vergleich|marktplatz|jobbörse|stellenmarkt)", text):
        return "Portal / Vergleichsplattform"
    return "Anbieter aus der HR-/Personaldienstleistungs-Branche"


def position_weight(position: int) -> float:
    if position <= 3:
        return 1.0
    if position <= 10:
        return 0.6
    if position <= 20:
        return 0.3
    return 0.15


def volume_factor(volume: int | None) -> float:
    if volume is None or volume < 10:
        return 1.0
    if volume < 100:
        return 1.15
    if volume < 1000:
        return 1.3
    if volume < 10000:
        return 1.6
    return 2.0


def lost_keywords(
    own: DomainProfile,
    competitor: DomainProfile,
    cfg: Config,
    volumes: dict[str, int] | None = None,
) -> tuple[list[LostKeyword], int]:
    volumes = volumes or {}
    own_map = own.keyword_map()
    comp_map = competitor.keyword_map()
    lost: list[LostKeyword] = []
    overlap = 0
    for keyword, comp_rank in comp_map.items():
        own_rank = own_map.get(keyword)
        volume = volumes.get(keyword)
        if own_rank is not None:
            overlap += 1
            if comp_rank.position < own_rank.position:
                gap = own_rank.position - comp_rank.position
                lost.append(
                    LostKeyword(
                        keyword=keyword,
                        competitor_position=comp_rank.position,
                        own_position=own_rank.position,
                        own_url=own_rank.url,
                        competitor_url=comp_rank.url,
                        gap=gap,
                        score=gap * position_weight(comp_rank.position) * volume_factor(volume),
                        search_volume=volume,
                    )
                )
        elif cfg.assume_unranked_if_not_fetched and comp_rank.position <= 10:
            lost.append(
                LostKeyword(
                    keyword=keyword,
                    competitor_position=comp_rank.position,
                    own_position=None,
                    own_url="",
                    competitor_url=comp_rank.url,
                    gap=None,
                    score=5.0 * position_weight(comp_rank.position) * volume_factor(volume),
                    search_volume=volume,
                )
            )
    lost.sort(key=lambda item: item.score, reverse=True)
    return lost, overlap


def danger_score(competitor: DomainProfile, own: DomainProfile, lost: list[LostKeyword], overlap: int) -> float:
    weighted_lost = sum(item.score for item in lost)
    visindex = competitor.visindex or 0.0
    own_visindex = own.visindex or 0.0
    vi_ratio = (visindex / own_visindex) if own_visindex else 0.0
    return weighted_lost * 2.0 + overlap * 0.5 + min(vi_ratio, 5.0) * 2.0


def build_competitor_report(
    own: DomainProfile,
    competitor: DomainProfile,
    cfg: Config,
    volumes: dict[str, int] | None = None,
) -> CompetitorReport:
    lost, overlap = lost_keywords(own, competitor, cfg, volumes=volumes)
    business_type = classify_business(competitor, cfg)
    top = lost[: cfg.keywords_per_competitor]

    sample_keywords = ", ".join(competitor.top_keywords[:5]) or "–"
    relevance_reasons = [
        f"Geschäftsmodell laut eigener Top-Keywords: {business_type} (z. B. „{sample_keywords}“).",
        f"Domain {competitor.domain} erscheint in der Sistrix-Wettbewerberliste von {own.domain}.",
    ]
    own_vi = f"{own.visindex:.4f}" if own.visindex is not None else "k. A."
    comp_vi = f"{competitor.visindex:.4f}" if competitor.visindex is not None else "k. A."
    comp_top10 = competitor.kwcount_top10 if competitor.kwcount_top10 is not None else 0
    danger_reasons = [
        f"Sichtbarkeitsindex {comp_vi} vs. {own_vi} bei {own.domain} (Land {cfg.country}).",
        f"{comp_top10} Keywords in den organischen Top 10; {overlap} Keywords überschneiden sich mit uns im Ranking.",
        f"{len(lost)} Keywords ranken wir schlechter als {competitor.domain} (davon {sum(1 for i in lost if i.own_position is None)} Keywords, für die wir in den Top {cfg.max_pos} gar nicht ranken).",
    ]
    return CompetitorReport(
        profile=competitor,
        business_type=business_type,
        overlap=overlap,
        lost=lost,
        top_to_optimize=top,
        relevance_reasons=relevance_reasons,
        danger_reasons=danger_reasons,
    )


def select_top_competitors(
    own: DomainProfile, candidates: list[DomainProfile], cfg: Config
) -> list[CompetitorReport]:
    relevant = [p for p in candidates if is_branch_relevant(p, cfg)]
    scored: list[tuple[float, CompetitorReport]] = []
    for profile in relevant:
        lost, overlap = lost_keywords(own, profile, cfg)
        score = danger_score(profile, own, lost, overlap)
        report = build_competitor_report(own, profile, cfg)
        scored.append((score, report))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [report for _, report in scored[: cfg.top_competitors]]
