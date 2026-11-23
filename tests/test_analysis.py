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
    volume_factor,
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


def test_keyword_row_cap_applies_to_all_domains():
    import asyncio as _asyncio

    cfg = Config(max_keywords_per_domain=2)
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
                "keywords": [{"keyword": "interim a", "position": 1}, {"keyword": "interim b", "position": 2}, {"keyword": "interim c", "position": 3}],
            }
        ],
        "assume_unranked_if_not_fetched": False,
    }
    result = _asyncio.run(run_weekly_analysis(StaticSistrixClient(capture), cfg))
    assert len(result.own.keywords) <= 2
    assert len(result.competitors[0].profile.keywords) <= 2


def test_run_weekly_analysis_on_live_capture():
    capture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "live_capture.json"
    )
    with open(capture_path, encoding="utf-8") as fh:
        capture = json.load(fh)
    cfg = Config()
    cfg.assume_unranked_if_not_fetched = False
    cfg.max_keywords_per_domain = 10000
    result = asyncio.run(run_weekly_analysis(StaticSistrixClient(capture), cfg))
    assert result.own_domain == "deutscheinterim.com"
    assert len(result.competitors) == 3
    for comp in result.competitors:
        assert 1 <= len(comp.top_to_optimize) <= 5
        assert comp.overlap >= 0
        assert comp.lost
        for item in comp.top_to_optimize:
            assert item.competitor_position < (item.own_position or 999)
    volumes_seen = [
        i.search_volume
        for c in result.competitors
        for i in c.top_to_optimize
        if i.search_volume is not None
    ]
    assert volumes_seen


def test_volume_factor_tiers():
    assert volume_factor(None) == 1.0
    assert volume_factor(0) == 1.0
    assert volume_factor(9) == 1.0
    assert volume_factor(10) == 1.15
    assert volume_factor(99) == 1.15
    assert volume_factor(100) == 1.3
    assert volume_factor(999) == 1.3
    assert volume_factor(1000) == 1.6
    assert volume_factor(9999) == 1.6
    assert volume_factor(10000) == 2.0


def test_search_volume_changes_lost_keyword_order():
    cfg = Config()
    own = make_profile(
        "deutscheinterim.com",
        [("interim manager berlin", 20), ("interim coo projekt", 20)],
    )
    comp = make_profile(
        "interim-profis.com",
        [("interim manager berlin", 10), ("interim coo projekt", 10)],
    )
    volumes = {"interim coo projekt": 8100, "interim manager berlin": 90}
    lost_plain, _ = lost_keywords(own, comp, cfg)
    lost_vol, _ = lost_keywords(own, comp, cfg, volumes=volumes)
    assert {i.keyword for i in lost_plain} == {"interim manager berlin", "interim coo projekt"}
    assert lost_plain[0].score == lost_plain[1].score
    assert lost_vol[0].keyword == "interim coo projekt"
    by_kw = {i.keyword: i for i in lost_vol}
    assert by_kw["interim coo projekt"].search_volume == 8100
    assert by_kw["interim manager berlin"].search_volume == 90
    assert by_kw["interim coo projekt"].score > by_kw["interim manager berlin"].score


def test_search_volume_lookup_is_capped_and_applied():
    class RecordingClient(StaticSistrixClient):
        def __init__(self, capture):
            super().__init__(capture)
            self.requested = []

        async def search_volumes(self, keywords, country):
            self.requested.extend(keywords)
            return await super().search_volumes(keywords, country)

    capture = {
        "own": {
            "domain": "deutscheinterim.com",
            "visindex": 0.1,
            "keywords": [
                {"keyword": "interim a", "position": 5},
                {"keyword": "interim b", "position": 6},
                {"keyword": "interim c", "position": 7},
                {"keyword": "interim d", "position": 8},
            ],
        },
        "competitor_list": ["interim-profis.com"],
        "competitor_candidates": [
            {
                "domain": "interim-profis.com",
                "visindex": 0.2,
                "kwcount_top10": 10,
                "top_keywords": ["interim a"],
                "keywords": [
                    {"keyword": "interim a", "position": 1},
                    {"keyword": "interim b", "position": 2},
                    {"keyword": "interim c", "position": 3},
                    {"keyword": "interim d", "position": 4},
                    {"keyword": "interim e", "position": 1},
                ],
            }
        ],
        "search_volumes": {"interim a": 8100, "interim e": 40},
        "assume_unranked_if_not_fetched": True,
    }
    cfg = Config(search_volume_lookup_limit=2)
    client = RecordingClient(capture)
    result = asyncio.run(run_weekly_analysis(client, cfg))
    assert len(client.requested) <= 2
    top = result.competitors[0].top_to_optimize
    assert top[0].keyword == "interim a"
    assert top[0].search_volume == 8100


def test_row_level_traffic_used_as_search_volume():
    capture = {
        "own": {
            "domain": "deutscheinterim.com",
            "visindex": 0.1,
            "keywords": [
                {"keyword": "interim a", "position": 20},
                {"keyword": "interim b", "position": 20},
            ],
        },
        "competitor_list": ["interim-profis.com"],
        "competitor_candidates": [
            {
                "domain": "interim-profis.com",
                "visindex": 0.2,
                "kwcount_top10": 10,
                "top_keywords": ["interim a"],
                "keywords": [
                    {"keyword": "interim a", "position": 10, "traffic": 90},
                    {"keyword": "interim b", "position": 10, "traffic": 8100},
                ],
            }
        ],
        "assume_unranked_if_not_fetched": False,
    }
    cfg = Config(search_volume_lookup_limit=0)
    result = asyncio.run(run_weekly_analysis(StaticSistrixClient(capture), cfg))
    top = result.competitors[0].top_to_optimize
    assert top[0].keyword == "interim b"
    assert top[0].search_volume == 8100
