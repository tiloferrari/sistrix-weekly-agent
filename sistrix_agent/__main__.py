from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date

from .agent import run_weekly_analysis
from .client import RestSistrixClient, StaticSistrixClient
from .config import Config
from .report import build_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Wöchentliche Sistrix-Wettbewerbsanalyse mit PDF-Bericht")
    parser.add_argument("--client", choices=["rest", "static"], default="rest")
    parser.add_argument("--data", help="Pfad zu einem aufgezeichneten Sistrix-Capture (nur --client static)")
    parser.add_argument("--output", help="Ausgabepfad für den PDF-Bericht")
    parser.add_argument("--country", default=None)
    args = parser.parse_args()

    cfg = Config.from_env()
    if args.country:
        cfg.country = args.country

    if args.client == "static":
        if not args.data:
            parser.error("--data ist für --client static erforderlich")
        with open(args.data, encoding="utf-8") as fh:
            capture = json.load(fh)
        client = StaticSistrixClient(capture)
        if capture.get("assume_unranked_if_not_fetched") is not None:
            cfg.assume_unranked_if_not_fetched = bool(capture["assume_unranked_if_not_fetched"])
    else:
        client = RestSistrixClient()

    result = asyncio.run(run_weekly_analysis(client, cfg))

    output = args.output or os.path.join(
        "reports", f"sistrix-weekly-report-{date.today().isoformat()}.pdf"
    )
    path = build_pdf(result, output)
    print(f"PDF-Bericht erstellt: {path}")
    print(f"Top-{cfg.top_competitors}-Wettbewerber: " + ", ".join(c.profile.domain for c in result.competitors))


if __name__ == "__main__":
    main()
