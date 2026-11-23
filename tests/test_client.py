import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistrix_agent.client import RestSistrixClient


def test_find_error_detects_nested_error_shapes():
    find = RestSistrixClient._find_error
    assert find({"error": [{"error_code": 403, "error_message": "Permission denied"}]}) is not None
    assert find({"status": "error", "error": [{"error_code": 403}]}) is not None
    assert find({"answer": {"error": [{"error_code": 200, "error_message": "not enough credits"}]}}) is not None
    assert find({"answer": [{"error_code": 200, "error_message": "not enough credits"}]}) is not None
    assert find({"answer": {"data": [{"error_message": "boom"}]}}) is not None


def test_find_error_ignores_clean_payloads():
    find = RestSistrixClient._find_error
    assert find({"answer": {"sichtbarkeitsindex": [{"value": "0.1015"}]}}) is None
    assert find({"answer": {}}) is None
    assert find([{"kw": "interim manager", "position": 1, "url": "https://x.de/"}]) is None
    assert find(None) is None
    assert find("text") is None


def test_rest_parsing_handles_answer_list_envelope():
    # Envelope wie von api.sistrix.com (format=json) beobachtet am 2026-11-23:
    # answer ist eine LISTE von Dicts, z. B. [{"sichtbarkeitsindex": [rows]}] oder [{"result": [rows]}]
    visindex_payload = {
        "method": [["domain.visibilityindex"]],
        "info": [{"country": "de", "domain": "deutscheinterim.com"}],
        "answer": [{"sichtbarkeitsindex": [{"domain": "deutscheinterim.com", "date": "2026-11-23", "value": "0.0906"}]}],
        "credits": [{"used": 1}],
    }
    assert RestSistrixClient._scalar(visindex_payload) == 0.0906

    comp_payload = {
        "method": [["domain.competitors.seo"]],
        "info": [{"country": "de", "device": "mobile", "domain": "deutscheinterim.com"}],
        "answer": [{"result": [
            {"domain": "deutscheinterim.com", "match": 100},
            {"domain": "linkedin.com", "match": 45.8},
            {"domain": "https://www.interim-profis.com/path", "match": 30.0},
        ]}],
        "credits": [{"used": 5}],
    }
    domains = RestSistrixClient._extract_domains(comp_payload)
    assert domains == ["deutscheinterim.com", "linkedin.com", "interim-profis.com"]

    kw_payload = {
        "answer": [{"result": [
            {"kw": "deutsche interim ag", "position": 1, "competition": 18, "traffic": 200, "url": "https://www.deutscheinterim.com/de"},
            {"kw": "interimmanagement", "position": 1, "url": "https://www.deutscheinterim.com/de/x"},
        ]}],
    }
    rows = [
        d for d in RestSistrixClient._walk_dicts(RestSistrixClient._unwrap_answer(kw_payload))
        if isinstance(d.get("kw"), str) and "position" in d
    ]
    assert [r["kw"] for r in rows] == ["deutsche interim ag", "interimmanagement"]

    # alte Envelope (answer als Dict mit data / bare list) weiter unterstuetzt
    assert RestSistrixClient._scalar({"answer": {"data": [{"value": 1.5}]}}) == 1.5
    assert RestSistrixClient._extract_domains({"answer": ["a.de", "b.de", "a.de"]}) == ["a.de", "b.de"]


def test_parse_rank_reads_traffic_as_search_volume():
    parse = RestSistrixClient._parse_rank
    rank = parse({"kw": "deutsche interim ag", "position": 1, "competition": 18, "traffic": 200, "url": "https://www.deutscheinterim.com/de"})
    assert rank is not None
    assert rank.keyword == "deutsche interim ag"
    assert rank.position == 1
    assert rank.search_volume == 200
    assert parse({"kw": "x", "position": 3}).search_volume is None
    assert parse({"position": 3}) is None
    assert parse({"kw": "x"}) is None
