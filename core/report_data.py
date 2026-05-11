"""Report Data — POJO that bundles all Mode A outputs for PDF generation.

Architecture:
    ReportData is a pure data carrier. It does NOT compute. The Stage 1 pipeline
    (buildable_zone -> indicators -> verifier -> site_planner) computes results;
    `from_pipeline(...)` adapts them into a single ReportData for the renderer.

Companion modules:
    core/report_renderer.py — turns ReportData into matplotlib figures
    core/report_pdf.py      — assembles figures + text into 9-page PDF
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default average apartment size (m²) used for estimate_units().
# This is M3 standard per PL practice — sourced from APARTMENT_MIN_AREA in pack.
DEFAULT_AVG_APARTMENT_M2 = 55.0

TOOL_VERSION = "0.5.0-phase2"


@dataclass
class SetbackInfo:
    """Setback distances applied to compute buildable zone."""
    front_m: float = 0.0
    side_m: float = 0.0
    rear_m: float = 0.0


@dataclass
class MPZPSummary:
    """Human-readable MPZP parameters for the report Dane Wejściowe page."""
    przeznaczenie: str = ""        # "MN" / "MW"
    wz_max: float = 0.0            # max coverage ratio
    wiz_max: float = 0.0           # max intensity
    pbc_min_percent: float = 0.0   # min bio-active %
    max_height_m: float = 0.0
    typ_zabudowy: str = ""         # "jednorodzinna" / "wielorodzinna"
    line_zabudowy_m: float = 0.0
    infrastructure_municipal: bool = True


@dataclass
class IndicatorRow:
    """One indicator (WZ/WIZ/PBC) for the report Wskaźniki page."""
    name: str            # "WZ", "WIZ", "PBC"
    designed: float
    limit: float
    unit: str            # "" (ratio) or "%"
    status: str          # "OK" / "WARN" / "VIOLATION"


@dataclass
class VariantInfo:
    """One buildup variant for the report Warianty page."""
    number: int
    footprint_area_m2: float
    wz: float
    wiz: float
    pbc_percent: float
    estimated_units: int      # PUM ÷ DEFAULT_AVG_APARTMENT_M2
    description: str = ""


@dataclass
class ComplianceRow:
    """One verification result for the report Compliance page."""
    rule_id: str
    rule_name: str
    designed_value_str: str
    required_value_str: str
    status: str               # "ZGODNY" / "NIEZGODNY" / "OSTRZEZENIE" / "NIEWERYFIKOWANY"
    legal_basis: str


@dataclass
class ReportData:
    """All data needed to render a feasibility report PDF."""
    # === Required identification ===
    plot_id: str
    plot_address: str
    plot_area_m2: float

    # === Plot geometry (optional, with defaults) ===
    plot_perimeter_m: float = 0.0
    plot_polygon_wkt: str = ""             # Shapely WKT for serialization/hash
    buildable_polygon_wkt: str = ""

    # === MPZP ===
    mpzp_summary: MPZPSummary = field(default_factory=MPZPSummary)

    # === Buildable zone ===
    buildable_zone_m2: float = 0.0
    buildable_zone_percent: float = 0.0
    setbacks: SetbackInfo = field(default_factory=SetbackInfo)

    # === Indicators (3 rows: WZ, WIZ, PBC) ===
    indicators: List[IndicatorRow] = field(default_factory=list)

    # === Compliance (19 rows for WT 2002 PL pack) ===
    verification_results: List[ComplianceRow] = field(default_factory=list)

    # === Variants (3 from site_planner.propose_max_buildup) ===
    buildup_variants: List[VariantInfo] = field(default_factory=list)

    # === White-label / metadata ===
    logo_path: Optional[Path] = None        # if set, embedded on cover + footer
    generated_at: datetime = field(default_factory=datetime.now)
    tool_version: str = TOOL_VERSION
    pack_version: str = "PL/1.0"

    # === Computed at render time ===
    data_hash: str = ""                     # set by compute_hash()
