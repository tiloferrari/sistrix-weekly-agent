from __future__ import annotations

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import AnalysisResult


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=18, leading=22, spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=10, leading=14, textColor=colors.HexColor("#555555")),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=14, leading=18, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, leading=16, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=9.5, leading=13, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=8, leading=10),
        "cellhead": ParagraphStyle("cellhead", parent=base["Normal"], fontSize=8, leading=10, fontName="Helvetica-Bold", textColor=colors.white),
    }


def _fmt_pos(position: int | None) -> str:
    return str(position) if position is not None else f"nicht in Top 100"


def _table(data: list[list[str]], widths: list[float], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(cell, styles["cellhead"]) for cell in data[0]]]
    rows += [[Paragraph(cell, styles["cell"]) for cell in row] for row in data[1:]]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f8")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_pdf(result: AnalysisResult, output_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"SEO-Wettbewerbsanalyse {result.company_name}",
        author="Sistrix Weekly Agent",
    )
    story: list = []

    story.append(Paragraph(f"Wochenbericht: SEO-Wettbewerbsanalyse", styles["title"]))
    story.append(
        Paragraph(
            f"{result.company_name} · Domain <b>{result.own_domain}</b> · Google-Land: <b>{result.country}</b> · "
            f"Erstellt am {datetime.now().strftime('%d.%m.%Y')} · Datenquelle: Sistrix (Connector)",
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    own = result.own
    own_vi = f"{own.visindex:.4f}" if own.visindex is not None else "k. A."
    own_kw = own.kwcount if own.kwcount is not None else len(own.keywords)
    own_top10 = own.kwcount_top10 if own.kwcount_top10 is not None else 0
    story.append(Paragraph("1. Ausgangslage", styles["h1"]))
    story.append(
        Paragraph(
            f"{result.own_domain} hat aktuell einen Sichtbarkeitsindex von <b>{own_vi}</b>, "
            f"ranked für <b>{own_kw}</b> organische Keywords und für <b>{own_top10}</b> Keywords in den Top 10. "
            "Dieser Bericht zeigt die drei Wettbewerber aus der Interim-/Personal-Branche, die im SEO-Ranking am gefährlichsten sind, "
            "und je Wettbewerber bis zu 5 Keywords, bei denen wir schlechter ranken und unseren Content optimieren sollten.",
            styles["body"],
        )
    )

    story.append(Paragraph("2. Top-3-Wettbewerber im Überblick", styles["h1"]))
    overview = [["Wettbewerber", "Typ", "Sichtbarkeitsindex", "Top-10-Keywords", "Keyword-Überschneidung", "Verlorene Keywords"]]
    for comp in result.competitors:
        comp_vi = f"{comp.profile.visindex:.4f}" if comp.profile.visindex is not None else "k. A."
        comp_top10 = comp.profile.kwcount_top10 if comp.profile.kwcount_top10 is not None else 0
        overview.append(
            [
                comp.profile.domain,
                comp.business_type,
                comp_vi,
                str(comp_top10),
                str(comp.overlap),
                str(len(comp.lost)),
            ]
        )
    story.append(_table(overview, [3.2 * cm, 4.2 * cm, 2.6 * cm, 2.4 * cm, 2.7 * cm, 2.7 * cm], styles))

    story.append(Paragraph("3. Methodik", styles["h1"]))
    for step in [
        "Schritt 1: Wettbewerber-Kandidaten über die Sistrix-Wettbewerberliste von " + result.own_domain + " ermitteln und auf Branchenrelevanz filtern (Interim-Provider, Personalberatungen, Personalvermittler; Portale und Enzyklopädien ausgeschlossen).",
        "Schritt 2: Pro Kandidat ein Kurzprofil erstellen: Geschäftsmodell anhand der eigenen Top-Keywords, Sichtbarkeitsindex, Anzahl Top-10-Keywords und Keyword-Überschneidung mit uns. Daraus die 3 gefährlichsten Wettbewerber auswählen (Gewichtung: verlorene Keywords, Überschneidung, Sichtbarkeit).",
        "Schritt 3: Für jeden Top-Wettbewerber alle Keywords im Wettbewerb mit uns vergleichen (Sistrix: keyword_domain_seo, Positionen bis Top " + "100" + ") und die Keywords ermitteln, bei denen der Wettbewerber besser rankt als wir.",
        "Schritt 4: Pro Wettbewerber die 5 Keywords mit dem höchsten Optimierungspotenzial (Position des Wettbewerbers × Positionsdifferenz) als Content-Empfehlung ausgeben.",
    ]:
        story.append(Paragraph(step, styles["bullet"], bulletText="•"))

    for index, comp in enumerate(result.competitors, start=1):
        story.append(Paragraph(f"4.{index} Wettbewerber: {comp.profile.domain}", styles["h1"]))
        story.append(Paragraph(f"Kurzprofil ({comp.business_type})", styles["h2"]))
        comp_vi = f"{comp.profile.visindex:.4f}" if comp.profile.visindex is not None else "k. A."
        comp_top10 = comp.profile.kwcount_top10 if comp.profile.kwcount_top10 is not None else 0
        story.append(
            Paragraph(
                f"Domain <b>{comp.profile.domain}</b> · Sichtbarkeitsindex <b>{comp_vi}</b> · "
                f"<b>{comp_top10}</b> Top-10-Keywords · eigene Top-Keywords: "
                + ", ".join(f"„{k}“" for k in comp.profile.top_keywords[:6]),
                styles["body"],
            )
        )
        story.append(Paragraph("Warum ist dieser Wettbewerber für uns relevant?", styles["h2"]))
        for reason in comp.relevance_reasons:
            story.append(Paragraph(reason, styles["bullet"], bulletText="•"))
        story.append(Paragraph("Warum ist er aus SEO-Sicht gefährlich?", styles["h2"]))
        for reason in comp.danger_reasons:
            story.append(Paragraph(reason, styles["bullet"], bulletText="•"))

        story.append(Paragraph("Top-5-Keywords zur Content-Optimierung", styles["h2"]))
        rows = [["Keyword", "Unsere Position", "Wettbewerber-Position", "Unsere URL", "Wettbewerber-URL"]]
        for item in comp.top_to_optimize:
            rows.append(
                [
                    item.keyword,
                    _fmt_pos(item.own_position),
                    str(item.competitor_position),
                    item.own_url or "–",
                    item.competitor_url or "–",
                ]
            )
        story.append(_table(rows, [4.6 * cm, 2.2 * cm, 2.6 * cm, 4.2 * cm, 4.2 * cm], styles))
        story.append(Spacer(1, 0.2 * cm))

    story.append(Spacer(1, 0.4 * cm))
    story.append(
        Paragraph(
            "Hinweis: Positionen und Sichtbarkeitsindex stammen aus dem Sistrix-SEO-Monitoring (Google " + result.country + ") "
            "zum Zeitpunkt der Berichtserstellung. „Verlorene Keywords“ sind Keywords, für die beide Domains in den Top 100 ranken "
            "und der Wettbewerber eine bessere Position hat, bzw. Keywords in den Top 10 des Wettbewerbers, für die wir nicht in den Top 100 ranken.",
            styles["subtitle"],
        )
    )

    doc.build(story)
    return output_path
