"""Report PDF — assembles ReportData + matplotlib figures into a 9-page PDF.

Architecture:
    `generate_pdf(rd, output_path)` is the entry point. It composes the
    9-page report using reportlab's high-level Platypus API
    (SimpleDocTemplate + flowables: Paragraph, Image, Table, PageBreak).

    Each page is its own helper function (cover_page, exec_summary_page, ...)
    that returns a list of flowables. The main function concatenates them.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)
from reportlab.lib import colors

from core.report_data import ReportData, compute_hash


# --- Font registration (Latin Extended / Polish diacritics support) ---
# Arial Unicode covers full Latin-Extended-A (Polish ą ę ó ś ź ż ć ł ń).
# Falls back gracefully to Helvetica if the font file is missing (non-macOS).
_ARIAL_UNICODE_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_UNICODE_FONT = "Helvetica"  # fallback
try:
    pdfmetrics.registerFont(TTFont("ArialUnicode", _ARIAL_UNICODE_PATH))
    _UNICODE_FONT = "ArialUnicode"
except Exception:
    pass  # font file absent — Helvetica fallback (garbled diacritics but no crash)


# --- Style setup (module-level — reused across pages) ---

_styles = getSampleStyleSheet()
TITLE_STYLE = ParagraphStyle(
    name="Title", parent=_styles["Title"], fontSize=20, spaceAfter=12, alignment=1,  # center
    fontName=_UNICODE_FONT,
)
H1_STYLE = ParagraphStyle(
    name="H1", parent=_styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=8,
    fontName=_UNICODE_FONT,
)
BODY_STYLE = ParagraphStyle(
    name="Body", parent=_styles["BodyText"], fontSize=10, leading=13, spaceAfter=6,
    fontName=_UNICODE_FONT,
)
SMALL_STYLE = ParagraphStyle(
    name="Small", parent=_styles["BodyText"], fontSize=8, leading=10, textColor=colors.grey,
    fontName=_UNICODE_FONT,
)


# --- Page builders ---

def cover_page(rd: ReportData) -> List:
    """Page 1: cover with plot id, address, area, generation date, optional logo."""
    flowables: List = []

    if rd.logo_path and Path(rd.logo_path).is_file():
        flowables.append(Image(str(rd.logo_path), width=4 * cm, height=1.6 * cm))
        flowables.append(Spacer(1, 6 * mm))

    flowables.append(Paragraph("Raport analizy działki", TITLE_STYLE))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(Paragraph(rd.plot_address, BODY_STYLE))
    flowables.append(Paragraph(rd.plot_id, BODY_STYLE))
    flowables.append(Spacer(1, 10 * mm))

    summary_data = [
        ["Powierzchnia działki", f"{rd.plot_area_m2:.0f} m²"],
        ["Klasa zabudowy", rd.mpzp_summary.przeznaczenie or "—"],
        ["Wysokość max", f"{rd.mpzp_summary.max_height_m:.1f} m"],
        ["Wygenerowano", rd.generated_at.strftime("%Y-%m-%d %H:%M")],
        ["Wersja narzędzia", rd.tool_version],
        ["Pack regulacji", rd.pack_version],
    ]
    table = Table(summary_data, colWidths=[6 * cm, 6 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(table)
    flowables.append(PageBreak())
    return flowables


def exec_summary_page(rd: ReportData) -> List:
    """Page 2: top-line numbers."""
    flowables: List = []
    flowables.append(Paragraph("Podsumowanie (Executive summary)", H1_STYLE))

    wz_des = next((i.designed for i in rd.indicators if i.name == "WZ"), 0.0)
    wiz_des = next((i.designed for i in rd.indicators if i.name == "WIZ"), 0.0)
    pbc_des = next((i.designed for i in rd.indicators if i.name == "PBC"), 0.0)

    max_footprint = rd.plot_area_m2 * rd.mpzp_summary.wz_max
    max_pum = rd.plot_area_m2 * rd.mpzp_summary.wiz_max
    min_bio = rd.plot_area_m2 * rd.mpzp_summary.pbc_min_percent / 100.0

    n_errors = sum(1 for v in rd.verification_results if v.status == "NIEZGODNY")
    n_warns = sum(1 for v in rd.verification_results if v.status == "OSTRZEZENIE")

    summary_data = [
        ["Maks. powierzchnia zabudowy",
         f"{max_footprint:.0f} m²  (WZ max {rd.mpzp_summary.wz_max:.2f})"],
        ["Maks. PUM",
         f"{max_pum:.0f} m²  (WIZ max {rd.mpzp_summary.wiz_max:.2f})"],
        ["Min. powierzchnia bio-czynna",
         f"{min_bio:.0f} m²  (PBC min {rd.mpzp_summary.pbc_min_percent:.0f}%)"],
        ["Zalecane warianty zabudowy", f"{len(rd.buildup_variants)} (patrz strona 7)"],
        ["Naruszenia compliance", f"{n_errors} błędy / {n_warns} ostrzeżeń"],
    ]
    table = Table(summary_data, colWidths=[7 * cm, 9 * cm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(table)
    flowables.append(PageBreak())
    return flowables


def data_inputs_page(rd: ReportData) -> List:
    """Page 3: plot geometry + MPZP parameters."""
    flowables: List = []
    flowables.append(Paragraph("Dane wejściowe", H1_STYLE))
    flowables.append(Paragraph("<b>Działka</b>", BODY_STYLE))

    plot_data = [
        ["Powierzchnia", f"{rd.plot_area_m2:.1f} m²"],
        ["Obwód", f"{rd.plot_perimeter_m:.1f} m"],
        ["Strefa zabudowy", f"{rd.buildable_zone_m2:.0f} m² ({rd.buildable_zone_percent:.1f}%)"],
    ]
    t1 = Table(plot_data, colWidths=[5 * cm, 9 * cm])
    t1.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    flowables.append(t1)
    flowables.append(Spacer(1, 6 * mm))

    flowables.append(Paragraph("<b>Parametry MPZP</b>", BODY_STYLE))
    m = rd.mpzp_summary
    mpzp_data = [
        ["Przeznaczenie", m.przeznaczenie or "—"],
        ["WZ max", f"{m.wz_max:.2f}"],
        ["WIZ max", f"{m.wiz_max:.2f}"],
        ["PBC min", f"{m.pbc_min_percent:.0f}%"],
        ["Wysokość max", f"{m.max_height_m:.1f} m"],
        ["Typ zabudowy", m.typ_zabudowy or "—"],
        ["Linia zabudowy", f"{m.line_zabudowy_m:.1f} m"],
        ["Infrastruktura miejska", "tak" if m.infrastructure_municipal else "nie"],
    ]
    t2 = Table(mpzp_data, colWidths=[5 * cm, 9 * cm])
    t2.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    flowables.append(t2)
    flowables.append(PageBreak())
    return flowables


def generate_pdf(rd: ReportData, output_path: Path) -> Path:
    """Generate the full 9-page feasibility report PDF."""
    rd.data_hash = compute_hash(rd)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Raport feasibility — {rd.plot_id}",
        author="FloorPlan6",
    )

    flowables: List = []
    flowables.extend(cover_page(rd))
    flowables.extend(exec_summary_page(rd))
    flowables.extend(data_inputs_page(rd))

    doc.build(flowables)
    return output_path
