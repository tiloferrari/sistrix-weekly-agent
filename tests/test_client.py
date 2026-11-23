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
