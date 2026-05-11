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

from matplotlib.figure import Figure

from core.report_data import ReportData, compute_hash


# --- Font registration (Latin Extended / Polish diacritics support) ---
# Arial Unicode covers full Latin-Extended-A (Polish ą ę ó ś ź ż ć ł ń).
# Arial Bold gives visual emphasis with same Polish coverage.
# Falls back gracefully to Helvetica if the font files are missing (non-macOS).
_ARIAL_UNICODE_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_ARIAL_BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_UNICODE_FONT = "Helvetica"          # fallback
_UNICODE_FONT_BOLD = "Helvetica-Bold"  # fallback
try:
    pdfmetrics.registerFont(TTFont("ArialUnicode", _ARIAL_UNICODE_PATH))
    _UNICODE_FONT = "ArialUnicode"
except Exception:
    pass
try:
    pdfmetrics.registerFont(TTFont("ArialBold", _ARIAL_BOLD_PATH))
    _UNICODE_FONT_BOLD = "ArialBold"
except Exception:
    # Bold variant missing — fall back to regular Unicode font (still readable PL chars).
    _UNICODE_FONT_BOLD = _UNICODE_FONT


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


# --- Matplotlib → reportlab helper ---

def _figure_to_image(fig: Figure, max_width_cm: float = 17.0) -> Image:
    """Convert a matplotlib Figure to a reportlab Image flowable (in-memory)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    # Compute height by aspect ratio
    w_in, h_in = fig.get_size_inches()
    aspect = h_in / w_in
    width_cm = max_width_cm
    height_cm = width_cm * aspect
    return Image(buf, width=width_cm * cm, height=height_cm * cm)


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
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
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
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]))
    flowables.append(t2)
    flowables.append(PageBreak())
    return flowables


def buildable_zone_page(rd: ReportData) -> List:
    """Page 4: buildable zone figure + setback summary."""
    from core.report_renderer import plot_zone_figure
    flowables: List = []
    flowables.append(Paragraph("Strefa zabudowy (Buildable zone)", H1_STYLE))
    fig = plot_zone_figure(rd)
    flowables.append(_figure_to_image(fig))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(Paragraph(
        f"Strefa zabudowy: <b>{rd.buildable_zone_m2:.0f} m²</b> "
        f"({rd.buildable_zone_percent:.1f}% działki).",
        BODY_STYLE,
    ))
    flowables.append(PageBreak())
    return flowables


def indicators_page(rd: ReportData) -> List:
    """Page 5: indicators bar chart + Q14 5% band explanation."""
    from core.report_renderer import indicators_bar_chart
    flowables: List = []
    flowables.append(Paragraph("Wskaźniki MPZP (WZ / WIZ / PBC)", H1_STYLE))
    fig = indicators_bar_chart(rd)
    flowables.append(_figure_to_image(fig))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(Paragraph(
        "<b>Pasmo 5% tolerancji (Q14):</b> wartości w zakresie limit … limit×1.05 "
        "są oznaczane jako ostrzeżenie. Powyżej 1.05×limit — naruszenie.",
        SMALL_STYLE,
    ))
    flowables.append(PageBreak())
    return flowables


def compliance_page(rd: ReportData) -> List:
    """Page 6: compliance table (19 WT rules)."""
    flowables: List = []
    flowables.append(Paragraph("Compliance check — Warunki Techniczne 2002", H1_STYLE))

    # Table header + rows
    header = ["ID", "Reguła", "Wartość", "Wymóg", "Status", "Podstawa"]
    rows = [header]
    for r in rd.verification_results:
        status_symbol = {
            "ZGODNY": "OK", "NIEZGODNY": "X", "OSTRZEZENIE": "!",
            "NIEWERYFIKOWANY": "?",
        }.get(r.status, "?")
        rows.append([
            r.rule_id,
            r.rule_name[:35] + ("…" if len(r.rule_name) > 35 else ""),
            r.designed_value_str,
            r.required_value_str,
            status_symbol,
            r.legal_basis[:25] + ("…" if len(r.legal_basis) > 25 else ""),
        ])

    table = Table(rows, colWidths=[1.5 * cm, 6 * cm, 2.5 * cm, 2.5 * cm, 1.5 * cm, 3 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
        ("FONTNAME", (0, 0), (-1, 0), _UNICODE_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flowables.append(table)
    flowables.append(PageBreak())
    return flowables


def variants_page(rd: ReportData) -> List:
    """Page 7: 3-up variants grid + estimated units."""
    from core.report_renderer import variants_grid_figure
    flowables: List = []
    flowables.append(Paragraph("Warianty zabudowy + potencjalne mieszkania", H1_STYLE))
    fig = variants_grid_figure(rd)
    flowables.append(_figure_to_image(fig))
    flowables.append(Spacer(1, 4 * mm))
    flowables.append(Paragraph(
        "<i>Szacunek liczby mieszkań</i> = PUM / 55 m² (średnia M3, PL standard). "
        "Realna liczba zależy od konkretnego rozkładu w Stage 4.",
        SMALL_STYLE,
    ))
    flowables.append(PageBreak())
    return flowables


def glossary_page(rd: ReportData) -> List:
    """Page 8: glossary for non-specialist readers (developer, client)."""
    from core.report_data import GLOSSARY
    flowables: List = []
    flowables.append(Paragraph("Słowniczek", H1_STYLE))
    flowables.append(Paragraph(
        "Krótkie wyjaśnienia terminów używanych w raporcie — dla architekta, "
        "dewelopera i klienta.",
        SMALL_STYLE,
    ))
    flowables.append(Spacer(1, 4 * mm))

    rows = [["Termin", "Wyjaśnienie"]]
    for term, definition in GLOSSARY.items():
        rows.append([term, definition])

    table = Table(rows, colWidths=[3 * cm, 14 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
        ("FONTNAME", (0, 0), (-1, 0), _UNICODE_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flowables.append(table)
    flowables.append(PageBreak())
    return flowables


DISCLAIMER_TEXT = (
    "Niniejszy raport ma charakter <b>informacyjny</b>. Wartości oraz zgodność "
    "z przepisami zostały obliczone na podstawie podanych parametrów MPZP i "
    "geometrii działki. Raport nie zastępuje decyzji urzędu, opinii architekta "
    "uprawnionego ani szczegółowego projektu budowlanego. FloorPlan6 nie "
    "ponosi odpowiedzialności za decyzje podjęte wyłącznie na podstawie tego "
    "raportu."
)


def metadata_page(rd: ReportData) -> List:
    """Page 9: metadata footer + disclaimer."""
    flowables: List = []
    flowables.append(Paragraph("Metadata + Disclaimer", H1_STYLE))

    meta_data = [
        ["Wygenerowano", rd.generated_at.strftime("%Y-%m-%d %H:%M:%S")],
        ["Wersja narzędzia", rd.tool_version],
        ["Pack regulacji", rd.pack_version],
        ["Hash danych wejściowych", rd.data_hash],
        ["Identyfikator działki", rd.plot_id],
    ]
    if rd.logo_path:
        meta_data.append(["Logo biura", str(rd.logo_path.name) if hasattr(rd.logo_path, "name") else str(rd.logo_path)])

    table = Table(meta_data, colWidths=[6 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _UNICODE_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flowables.append(table)
    flowables.append(Spacer(1, 10 * mm))

    flowables.append(Paragraph("<b>Disclaimer</b>", BODY_STYLE))
    flowables.append(Paragraph(DISCLAIMER_TEXT, BODY_STYLE))
    return flowables  # No PageBreak — last page


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
    flowables.extend(buildable_zone_page(rd))
    flowables.extend(indicators_page(rd))
    flowables.extend(compliance_page(rd))
    flowables.extend(variants_page(rd))
    flowables.extend(glossary_page(rd))
    flowables.extend(metadata_page(rd))

    doc.build(flowables)
    return output_path


def _cli() -> int:
    """CLI entry point. Usage:
        python -m core.report_pdf --fixture sample --out /tmp/report.pdf
    """
    import argparse
    parser = argparse.ArgumentParser(description="Generate FloorPlan6 feasibility PDF report")
    parser.add_argument("--fixture", choices=["sample"], default="sample",
                          help="Use built-in fixture data (sample only for now).")
    parser.add_argument("--out", required=True, type=Path,
                          help="Output PDF path.")
    args = parser.parse_args()

    if args.fixture == "sample":
        from tests.fixtures.sample_report import make_sample_report
        rd = make_sample_report()
    else:
        print(f"Unknown fixture: {args.fixture}")
        return 2

    generate_pdf(rd, args.out)
    print(f"Generated: {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())
