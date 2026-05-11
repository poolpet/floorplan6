"""Reusable ReportData fixture for report_renderer + report_pdf tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.report_data import (
    ComplianceRow, IndicatorRow, MPZPSummary, ReportData, SetbackInfo,
    VariantInfo,
)


def _full_wt_compliance_rows():
    """All 19 WT 2002 rules as a realistic mix of statuses.

    Reflects the rules in rules/PL/wt_rules.json. Used to make the sample
    fixture demonstrate a non-trivial compliance check page.
    """
    return [
        ComplianceRow(
            rule_id="wt_001",
            rule_name="Odległość od granicy — ściana z otworami",
            designed_value_str="6.0 m",
            required_value_str="≥ 3.0 m",
            status="ZGODNY",
            legal_basis="§ 12 ust. 1 pkt 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_002",
            rule_name="Odległość od granicy — ściana bez otworów",
            designed_value_str="4.0 m",
            required_value_str="≥ 1.5 m",
            status="ZGODNY",
            legal_basis="§ 12 ust. 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_003",
            rule_name="Odległość od granicy — budynek pow. 12 m",
            designed_value_str="—",
            required_value_str="≥ 4.0 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 12 ust. 1 pkt 1 WT",
        ),
        ComplianceRow(
            rule_id="wt_004",
            rule_name="Odległość studni od granicy działki",
            designed_value_str="4.5 m",
            required_value_str="≥ 7.5 m",
            status="OSTRZEZENIE",
            legal_basis="§ 31 ust. 1 WT",
        ),
        ComplianceRow(
            rule_id="wt_005",
            rule_name="Odległość studni od szamba",
            designed_value_str="—",
            required_value_str="≥ 15.0 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 31 ust. 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_006",
            rule_name="Odległość szamba od granicy",
            designed_value_str="—",
            required_value_str="≥ 7.5 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 36 ust. 1 WT",
        ),
        ComplianceRow(
            rule_id="wt_007",
            rule_name="Odległość szamba od własnego budynku",
            designed_value_str="—",
            required_value_str="≥ 5.0 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 36 ust. 2 pkt a WT",
        ),
        ComplianceRow(
            rule_id="wt_008",
            rule_name="Odległość szamba od sąsiedniego budynku",
            designed_value_str="—",
            required_value_str="≥ 7.5 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 36 ust. 2 pkt b WT",
        ),
        ComplianceRow(
            rule_id="wt_009",
            rule_name="Parking — odległość pow. 4 stanowisk",
            designed_value_str="—",
            required_value_str="≥ 7.0 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 19 ust. 3 WT",
        ),
        ComplianceRow(
            rule_id="wt_010",
            rule_name="Parking — odległość do 4 stanowisk",
            designed_value_str="3.5 m",
            required_value_str="≥ 3.0 m",
            status="ZGODNY",
            legal_basis="§ 19 ust. 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_011",
            rule_name="Śmietnik — odległość od okien/drzwi",
            designed_value_str="8.0 m",
            required_value_str="≥ 10.0 m",
            status="OSTRZEZENIE",
            legal_basis="§ 22 ust. 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_012",
            rule_name="Min. szerokość dojazdu pieszo-jezdnego",
            designed_value_str="3.5 m",
            required_value_str="≥ 3.0 m",
            status="ZGODNY",
            legal_basis="§ 14 ust. 2 WT",
        ),
        ComplianceRow(
            rule_id="wt_013",
            rule_name="Min. szerokość drogi pożarowej",
            designed_value_str="—",
            required_value_str="≥ 4.0 m",
            status="NIEWERYFIKOWANY",
            legal_basis="§ 15 ust. 1 WT",
        ),
        ComplianceRow(
            rule_id="wt_014",
            rule_name="Wskaźnik zabudowy (WZ)",
            designed_value_str="0.30",
            required_value_str="≤ 0.30",
            status="OSTRZEZENIE",
            legal_basis="MPZP — § 5 ust. 2 pkt 3",
        ),
        ComplianceRow(
            rule_id="wt_015",
            rule_name="Wskaźnik intensywności zabudowy (WIZ)",
            designed_value_str="0.45",
            required_value_str="≤ 0.45",
            status="ZGODNY",
            legal_basis="MPZP — § 5 ust. 2 pkt 4",
        ),
        ComplianceRow(
            rule_id="wt_016",
            rule_name="Powierzchnia biologicznie czynna (PBC)",
            designed_value_str="42.0%",
            required_value_str="≥ 35.0%",
            status="ZGODNY",
            legal_basis="MPZP — § 5 ust. 2 pkt 5",
        ),
        ComplianceRow(
            rule_id="wt_017",
            rule_name="Maksymalna wysokość zabudowy",
            designed_value_str="9.5 m",
            required_value_str="≤ 12.0 m",
            status="ZGODNY",
            legal_basis="MPZP — § 5 ust. 2 pkt 1",
        ),
        ComplianceRow(
            rule_id="wt_018",
            rule_name="Nieprzekraczalna linia zabudowy",
            designed_value_str="6.0 m",
            required_value_str="≥ 6.0 m",
            status="ZGODNY",
            legal_basis="MPZP — § 5 ust. 2 pkt 2",
        ),
        ComplianceRow(
            rule_id="wt_019",
            rule_name="Wymiary miejsca postojowego",
            designed_value_str="2.5 × 5.0 m",
            required_value_str="≥ 2.5 × 5.0 m",
            status="ZGODNY",
            legal_basis="§ 18 ust. 2 WT",
        ),
    ]


def make_sample_report() -> ReportData:
    """A complete sample ReportData for testing renderers.

    Mimics a realistic small detached single-family plot (~1247 m², MN zoning),
    with all 19 WT 2002 rules verified (mix of ZGODNY / OSTRZEZENIE /
    NIEWERYFIKOWANY for non-applicable rules), 3 buildup variants.
    """
    return ReportData(
        plot_id="dz. 1234/5, obręb 7-08-12",
        plot_address="ul. Przykładowa 12, 02-495 Warszawa (Ursus)",
        plot_area_m2=1247.0,
        plot_perimeter_m=143.5,
        plot_polygon_wkt="POLYGON ((0 0, 30 0, 30 41.5, 0 41.5, 0 0))",
        buildable_polygon_wkt="POLYGON ((4 6, 26 6, 26 37.5, 4 37.5, 4 6))",
        mpzp_summary=MPZPSummary(
            przeznaczenie="MN — zabudowa mieszkaniowa jednorodzinna",
            wz_max=0.30,
            wiz_max=0.45,
            pbc_min_percent=35.0,
            max_height_m=12.0,
            typ_zabudowy="jednorodzinna, wolnostojąca",
            line_zabudowy_m=6.0,
            infrastructure_municipal=True,
        ),
        buildable_zone_m2=682.0,
        buildable_zone_percent=54.7,
        setbacks=SetbackInfo(front_m=6.0, side_m=4.0, rear_m=4.0),
        indicators=[
            IndicatorRow(name="WZ", designed=0.30, limit=0.30, unit="", status="WARN"),
            IndicatorRow(name="WIZ", designed=0.45, limit=0.45, unit="", status="OK"),
            IndicatorRow(name="PBC", designed=42.0, limit=35.0, unit="%", status="OK"),
        ],
        verification_results=_full_wt_compliance_rows(),
        buildup_variants=[
            VariantInfo(number=1, footprint_area_m2=245.0, wz=0.196, wiz=0.30,
                        pbc_percent=48.0, estimated_units=2,
                        description="Wariant A — kompaktowy, 1 kondygnacja + poddasze"),
            VariantInfo(number=2, footprint_area_m2=320.0, wz=0.257, wiz=0.39,
                        pbc_percent=41.0, estimated_units=3,
                        description="Wariant B — średni, 2 kondygnacje"),
            VariantInfo(number=3, footprint_area_m2=374.0, wz=0.30, wiz=0.45,
                        pbc_percent=35.0, estimated_units=4,
                        description="Wariant C — maksymalny WZ, 2 kondygnacje + użytkowe poddasze"),
        ],
        generated_at=datetime(2026, 5, 11, 12, 0, 0),
        pack_version="PL/1.0",
    )


def make_sample_logo(path: Path) -> Path:
    """Generate a 200×80 white-label test logo. Returns the path."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(2.0, 0.8))
    ax.text(0.5, 0.5, "ARCHI STUDIO", ha="center", va="center",
            fontsize=14, weight="bold", color="#333")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#999")
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return path
