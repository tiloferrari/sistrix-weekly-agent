import base64
from datetime import date

import pydantic
import mistralai.workflows as workflows


class WeeklySeoInput(pydantic.BaseModel):
    own_domain: str = "deutscheinterim.com"
    country: str = "de"
    top_competitors: int = 3
    keywords_per_competitor: int = 5
    max_keywords_per_domain: int = 100
    search_volume_lookup_limit: int = 25


@workflows.activity(name="sistrix-weekly-analysis")
async def sistrix_weekly_analysis(payload: WeeklySeoInput) -> dict:
    from sistrix_agent.agent import run_weekly_analysis
    from sistrix_agent.client import RestSistrixClient
    from sistrix_agent.config import Config
    from sistrix_agent.report import build_pdf

    cfg = Config(
        own_domain=payload.own_domain,
        country=payload.country,
        top_competitors=payload.top_competitors,
        keywords_per_competitor=payload.keywords_per_competitor,
        max_keywords_per_domain=payload.max_keywords_per_domain,
        search_volume_lookup_limit=payload.search_volume_lookup_limit,
    )
    client = RestSistrixClient()
    result = await run_weekly_analysis(client, cfg)

    diagnostics = None
    if result.own.visindex is None or not result.competitors:
        diagnostics = {
            "trigger": "leere Sistrix-Antworten (visindex None oder keine Wettbewerber)",
            "visindex_json": client.raw_get(
                "domain.visibilityindex", {"domain": payload.own_domain, "country": payload.country}
            ),
            "visindex_xml": client.raw_get(
                "domain.visibilityindex", {"domain": payload.own_domain, "country": payload.country}, with_format=False
            ),
            "competitors": client.raw_get(
                "domain.competitors.seo", {"domain": payload.own_domain, "country": payload.country, "num": 5}
            ),
            "keywords": client.raw_get(
                "keyword.domain.seo",
                {"domain": payload.own_domain, "country": payload.country, "limit": 5, "to_pos": 100},
            ),
        }

    filename = f"sistrix-weekly-report-{date.today().isoformat()}.pdf"
    pdf_path = f"/tmp/{filename}"
    build_pdf(result, pdf_path)
    with open(pdf_path, "rb") as fh:
        pdf_base64 = base64.b64encode(fh.read()).decode("ascii")

    return {
        "report_date": date.today().isoformat(),
        "own_domain": result.own_domain,
        "own_visindex": result.own.visindex,
        "competitors": [
            {
                "domain": c.profile.domain,
                "business_type": c.business_type,
                "visindex": c.profile.visindex,
                "overlap": c.overlap,
                "lost_count": len(c.lost),
                "top_keywords": [
                    {
                        "keyword": k.keyword,
                        "own_position": k.own_position,
                        "competitor_position": k.competitor_position,
                        "search_volume": k.search_volume,
                        "score": k.score,
                    }
                    for k in c.top_to_optimize
                ],
            }
            for c in result.competitors
        ],
        "pdf_file_name": filename,
        "pdf_base64": pdf_base64,
        "diagnostics": diagnostics,
    }


@workflows.workflow.define(name="sistrix-weekly-seo-report")
class SistrixWeeklySeoReport:
    @workflows.workflow.entrypoint
    async def run(self, payload: WeeklySeoInput) -> dict:
        return await sistrix_weekly_analysis(payload)
