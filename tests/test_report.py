import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sistrix_agent.agent import run_weekly_analysis
from sistrix_agent.client import StaticSistrixClient
from sistrix_agent.config import Config
from sistrix_agent.report import build_pdf


def test_build_pdf_creates_valid_pdf():
    capture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "live_capture.json"
    )
    with open(capture_path, encoding="utf-8") as fh:
        capture = json.load(fh)
    cfg = Config()
    cfg.assume_unranked_if_not_fetched = False
    result = asyncio.run(run_weekly_analysis(StaticSistrixClient(capture), cfg))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bericht.pdf")
        build_pdf(result, out)
        with open(out, "rb") as fh:
            content = fh.read()
    assert content.startswith(b"%PDF")
    assert len(content) > 5000
