import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistrix_agent.agent import run_weekly_analysis
from sistrix_agent.analysis import (
    classify_business,
    is_branch_relevant,
    is_excluded,
    lost_keywords,
    select_top_competitors,
)
from sistrix_agent.client import StaticSistrixClient
from sistrix_agent.config import Config
from sistrix_agent.models import DomainProfile, KeywordRank


def make_profile(domain, keywords, visindex=0.1, kwcount_top10=100, top_keywords=None):
    ranks = [KeywordRank(keyword=k, position=p, url=f"https://{domain}/{k}") for k, p in keywords]
    return DomainProfile(
        domain=domain,
        visindex=visindex,
        kwcount=len(ranks),
        kwcount_top10=kwcount_top10,
        keywords=ranks,
        top_keywords=top_keywords or [k for k, _ in keywords[:5]],
    )


def test_excluded_domains():
    cfg = Config()
    assert is_excluded("wikipedia.org", cfg)
    assert is_excluded("de.wikipedia.org", cfg)
    assert not is_excluded("atreus.de", cfg)


def test_branch_relevance():
    cfg = Config()
    interim = make_profile("interim-profis.com", [("interim manager berlin", 1)], top_keywords=["interim manager berlin"])
    wiki = make_profile("wikipedia.org", [("interim manager", 1)], top_keywords=["interim manager"])
    recruiting = make_profile("example-hr.de", [("personalberatung", 1)], top_keywords=["personalberatung hamburg"])
    assert is_branch_relevant(interim, cfg)
    assert is_branch_relevant(recruiting, cfg)
    assert not is_branch_relevant(wiki, cfg)


def test_classify_business():
    cfg = Config()
    interim = make_profile("x-interim.de", [("interim manager", 1)])
    beratung = make_profile("page-personal.de", [("personalberatung", 1)], top_keywords=["personalberatung berlin"])
    assert classify_business(interim, cfg) == "Interim-Management-Provider"
    assert "Personalberatung" in classify_business(beratung, cfg)


def test_lost_keywords_only_when_competitor_better():
    cfg = Config()
    own = make_profile(
        "deutscheinterim.com",
        [("interim manager berlin", 5), ("interim coo", 1), ("was ist interim", 3)],
    )
    comp = make_profile(
        "interim-profis.com",
        [("interim manager berlin", 2), ("interim coo", 3), ("was ist interim", 1)],
    )
    lost, overlap = lost_keywords(own, comp, cfg)
    assert overlap == 3
    by_kw = {item.keyword: item for item in lost}
    assert "interim manager berlin" in by_kw
    assert by_kw["interim manager berlin"].own_position == 5
    assert by_kw["interim manager berlin"].competitor_position == 2
    assert by_kw["interim manager berlin"].gap == 3
    assert "interim coo" not in by_kw
    assert by_kw["was ist interim"].gap == 2
    assert lost[0].score >= lost[-1].score


def test_unranked_top10_keywords_counted_only_when_configured():
    own = make_profile("deutscheinterim.com", [("interim coo", 1)])
    comp = make_profile("interim-x.com", [("interim manager finden", 1), ("interim coo", 2)])
    cfg_on = Config(assume_unranked_if_not_fetched=True)
    cfg_off = Config(assume_unranked_if_not_fetched=False)
    lost_on, _ = lost_keywords(own, comp, cfg_on)
    lost_off, _ = lost_keywords(own, comp, cfg_off)
    assert any(i.keyword == "interim manager finden" and i.own_position is None for i in lost_on)
    assert not any(i.keyword == "interim manager finden" for i in lost_off)


def test_select_top_competitors_ranks_by_danger_and_limits():
    cfg = Config(top_competitors=2, keywords_per_competitor=5)
    own = make_profile(
        "deutscheinterim.com",
        [("interim manager finden", 11), ("interim management düsseldorf", 13), ("interim coo", 1)],
        visindex=0.1,
    )
    strong = make_profile(
        "interim-profis.com",
        [("interim manager finden", 1), ("interim management düsseldorf", 2), ("interim coo", 2)],
        visindex=0.2,
        kwcount_top10=500,
        top_keywords=["interim manager finden", "interim management düsseldorf"],
    )
    weak = make_profile(
        "interim-aid.de",
        [("interim coo", 2)],
        visindex=0.01,
        kwcount_top10=10,
        top_keywords=["interim coo"],
    )
    portal = make_profile(
        "stepstone.de",
        [("interim jobs", 1)],
        top_keywords=["interim jobs"],
    )
    reports = select_top_competitors(own, [strong, weak, portal], cfg)
    assert len(reports) == 2
    assert reports[0].profile.domain == "interim-profis.com"
    assert all(r.profile.domain != "stepstone.de" for r in reports)
    assert len(reports[0].top_to_optimize) <= 5
    assert reports[0].top_to_optimize[0].keyword == "interim management düsseldorf"


def test_keyword_row_cap_per_domain():
    cfg = Config(max_keywords_per_domain=3)
    own = make_profile("deutscheinterim.com", [("interim a", 1), ("interim b", 2), ("interim c", 3), ("interim d", 4)])
    comp = make_profile("interim-profis.com", [("interim a", 1)], top_keywords=["interim a"])
    import asyncio as _asyncio

    class CapClient(StaticSistrixClient):
        async def domain_keywords(self, domain, country, to_pos, regex_keyword=None, page_size=1000, max_pages=10):
            rows = await super().domain_keywords(domain, country, to_pos, regex_keyword, page_size, max_pages)
            assert len(rows) <= 3, "row cap not applied"
            return rows

    capture = {
        "own": {
            "domain": "deutscheinterim.com",
            "visindex": 0.1,
            "keywords": [{"keyword": k, "position": p} for k, p in [("interim a", 1), ("interim b", 2), ("interim c", 3), ("interim d", 4)]],
        },
        "competitor_list": ["interim-profis.com"],
        "competitor_candidates": [
            {
                "domain": "interim-profis.com",
                "visindex": 0.2,
                "kwcount_top10": 10,
                "top_keywords": ["interim a"],
                "keywords": [{"keyword": "interim a", "position": 1}],
            }
        ],
        "assume_unranked_if_not_fetched": False,
    }
    result = _asyncio.run(run_weekly_analysis(CapClient(capture), cfg))
    assert len(result.own.keywords) <= 3


def test_run_weekly_analysis_on_live_capture():
    capture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "live_capture.json"
    )
    with open(capture_path, encoding="utf-8") as fh:
        capture = json.load(fh)
    cfg = Config()
    cfg.assume_unranked_if_not_fetched = False
    result = asyncio.run(run_weekly_analysis(StaticSistrixClient(capture), cfg))
    assert result.own_domain == "deutscheinterim.com"
    assert len(result.competitors) == 3
    for comp in result.competitors:
        assert 1 <= len(comp.top_to_optimize) <= 5
        assert comp.overlap >= 0
        assert comp.lost
        for item in comp.top_to_optimize:
            assert item.competitor_position < (item.own_position or 999)
