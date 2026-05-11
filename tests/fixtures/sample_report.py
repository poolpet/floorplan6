"""Reusable ReportData fixture for report_renderer + report_pdf tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.report_data import (
    ComplianceRow, IndicatorRow, MPZPSummary, ReportData, SetbackInfo,
    VariantInfo,
)


def make_sample_report() -> ReportData:
    """A complete sample ReportData for testing renderers."""
    return ReportData(
        plot_id="dz. 1234/5, obręb 7-08-12",
        plot_address="ul. Przykładowa 12, Warszawa",
        plot_area_m2=1247.0,
        plot_perimeter_m=143.5,
        plot_polygon_wkt="POLYGON ((0 0, 30 0, 30 41.5, 0 41.5, 0 0))",
        buildable_polygon_wkt="POLYGON ((4 6, 26 6, 26 37.5, 4 37.5, 4 6))",
        mpzp_summary=MPZPSummary(
            przeznaczenie="MN",
            wz_max=0.30,
            wiz_max=0.45,
            pbc_min_percent=35.0,
            max_height_m=12.0,
            typ_zabudowy="jednorodzinna",
            line_zabudowy_m=6.0,
            infrastructure_municipal=True,
        ),
        buildable_zone_m2=682.0,
        buildable_zone_percent=54.7,
        setbacks=SetbackInfo(front_m=6.0, side_m=4.0, rear_m=4.0),
        indicators=[
            IndicatorRow(name="WZ", designed=0.30, limit=0.30, unit="", status="WARN"),
            IndicatorRow(name="WIZ", designed=0.45, limit=0.45, unit="", status="OK"),
            IndicatorRow(name="PBC", designed=35.0, limit=35.0, unit="%", status="OK"),
        ],
        verification_results=[
            ComplianceRow(
                rule_id="wt_001",
                rule_name="Odległość od granicy — ściana z otworami",
                designed_value_str="6.0 m",
                required_value_str="≥ 3.0 m",
                status="ZGODNY",
                legal_basis="§ 12 ust. 1 pkt 2 WT",
            ),
            ComplianceRow(
                rule_id="wt_004",
                rule_name="Odległość studni od granicy",
                designed_value_str="4.5 m",
                required_value_str="≥ 7.5 m",
                status="OSTRZEZENIE",
                legal_basis="§ 31 WT",
            ),
            ComplianceRow(
                rule_id="wt_009",
                rule_name="Min. liczba miejsc parkingowych",
                designed_value_str="2",
                required_value_str="≥ 2",
                status="ZGODNY",
                legal_basis="§ 18 WT + MPZP",
            ),
        ],
        buildup_variants=[
            VariantInfo(number=1, footprint_area_m2=245.0, wz=0.196, wiz=0.30,
                        pbc_percent=42.0, estimated_units=7,
                        description="Wariant A — kompaktowy"),
            VariantInfo(number=2, footprint_area_m2=320.0, wz=0.257, wiz=0.39,
                        pbc_percent=37.0, estimated_units=9,
                        description="Wariant B — średni"),
            VariantInfo(number=3, footprint_area_m2=374.0, wz=0.30, wiz=0.45,
                        pbc_percent=35.0, estimated_units=10,
                        description="Wariant C — max WZ"),
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
