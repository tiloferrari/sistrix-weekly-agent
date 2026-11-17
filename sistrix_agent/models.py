from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeywordRank:
    keyword: str
    position: int
    url: str = ""


@dataclass
class DomainProfile:
    domain: str
    visindex: float | None = None
    kwcount: int | None = None
    kwcount_top10: int | None = None
    keywords: list[KeywordRank] = field(default_factory=list)
    top_keywords: list[str] = field(default_factory=list)

    def keyword_map(self) -> dict[str, KeywordRank]:
        return {k.keyword: k for k in self.keywords}


@dataclass
class LostKeyword:
    keyword: str
    competitor_position: int
    own_position: int | None
    own_url: str
    competitor_url: str
    gap: int | None
    score: float


@dataclass
class CompetitorReport:
    profile: DomainProfile
    business_type: str
    overlap: int
    lost: list[LostKeyword]
    top_to_optimize: list[LostKeyword]
    relevance_reasons: list[str]
    danger_reasons: list[str]


@dataclass
class AnalysisResult:
    company_name: str
    own_domain: str
    country: str
    generated_at: str
    own: DomainProfile
    competitors: list[CompetitorReport]
