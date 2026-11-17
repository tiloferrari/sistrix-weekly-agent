import os
from datetime import date

import pydantic
import mistralai.workflows as workflows


class WeeklySeoInput(pydantic.BaseModel):
    own_domain: str = "deutscheinterim.com"
    country: str = "de"
    top_competitors: int = 3
    keywords_per_competitor: int = 5
    upload_file: bool = True


@workflows.activity(name="sistrix-weekly-analysis")
async def sistrix_weekly_analysis(payload: WeeklySeoInput) -> dict:
    from mistralai.client import Mistral

    from sistrix_agent.agent import run_weekly_analysis
    from sistrix_agent.client import RestSistrixClient
    from sistrix_agent.config import Config
    from sistrix_agent.report import build_pdf

    cfg = Config(
        own_domain=payload.own_domain,
        country=payload.country,
        top_competitors=payload.top_competitors,
        keywords_per_competitor=payload.keywords_per_competitor,
    )
    client = RestSistrixClient()
    result = await run_weekly_analysis(client, cfg)

    filename = f"sistrix-weekly-report-{date.today().isoformat()}.pdf"
    pdf_path = f"/tmp/{filename}"
    build_pdf(result, pdf_path)

    file_id = None
    if payload.upload_file:
        api_key = os.environ.get("MISTRAL_API_KEY")
        async with Mistral(api_key=api_key) as mistral_client:
            with open(pdf_path, "rb") as fh:
                uploaded = await mistral_client.files.upload_async(
                    file={"file_name": filename, "content": fh}
                )
            file_id = uploaded.id

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
                    }
                    for k in c.top_to_optimize
                ],
            }
            for c in result.competitors
        ],
        "pdf_file_name": filename,
        "pdf_file_id": file_id,
    }


@workflows.workflow.define(name="sistrix-weekly-seo-report")
class SistrixWeeklySeoReport:
    @workflows.workflow.entrypoint
    async def run(self, payload: WeeklySeoInput) -> dict:
        return await sistrix_weekly_analysis(payload)
