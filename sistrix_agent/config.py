from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    own_domain: str = "deutscheinterim.com"
    company_name: str = "Deutsche Interim AG"
    country: str = "de"
    top_competitors: int = 3
    keywords_per_competitor: int = 5
    max_pos: int = 100
    max_keywords_per_domain: int = 100
    page_size: int = 1000
    max_pages: int = 10
    competitor_list_limit: int = 30
    branch_regex: str = (
        r"(?i)(interim|personal|recruit|vermittl|headhunt|personaldienstl"
        r"|zeitarbeit|talent|besetzung|führungskraft|fachkraft|\bhr\b)"
    )
    excluded_domains: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "wikipedia.org",
                "youtube.com",
                "linkedin.com",
                "indeed.com",
                "stepstone.de",
                "xing.com",
                "gabler.de",
                "linguee.de",
                "ihk.de",
                "haufe-akademie.de",
            }
        )
    )
    assume_unranked_if_not_fetched: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            own_domain=os.environ.get("SISTRIX_OWN_DOMAIN", cls.own_domain),
            company_name=os.environ.get("SISTRIX_COMPANY_NAME", cls.company_name),
            country=os.environ.get("SISTRIX_COUNTRY", cls.country),
            top_competitors=int(os.environ.get("SISTRIX_TOP_COMPETITORS", cls.top_competitors)),
            keywords_per_competitor=int(
                os.environ.get("SISTRIX_KEYWORDS_PER_COMPETITOR", cls.keywords_per_competitor)
            ),
            max_pos=int(os.environ.get("SISTRIX_MAX_POS", cls.max_pos)),
            max_keywords_per_domain=int(
                os.environ.get("SISTRIX_MAX_KEYWORDS_PER_DOMAIN", cls.max_keywords_per_domain)
            ),
        )
