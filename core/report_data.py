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
    estimated_units: int            # PUM ÷ DEFAULT_AVG_APARTMENT_M2 (apartments OR houses)
    description: str = ""           # short label, e.g. "Wariant A — kompaktowy"

    # === Detailed metrics (added in Phase 2 polish) ===
    pum_m2: float = 0.0             # Powierzchnia Użytkowa Mieszkaniowa (footprint × storeys × usable_factor)
    num_storeys: int = 1            # liczba kondygnacji nadziemnych
    height_m: float = 0.0           # szacunkowa wysokość budynku [m]
    wz_headroom_percent: float = 0.0  # ile % poniżej WZ max — rezerwa
    pbc_headroom_percent: float = 0.0 # ile p.p. powyżej PBC min — rezerwa
    parking_spaces: int = 0         # zaprojektowane miejsca postojowe
    long_description: str = ""      # 2-3 zdania charakteryzujące wariant


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


def estimate_units(
    pum_m2: float,
    avg_apartment_m2: float = DEFAULT_AVG_APARTMENT_M2,
) -> int:
    """Estimate number of apartments fitting in usable area.

    PUM (Powierzchnia Użytkowa Mieszkaniowa) divided by typical apartment size.
    Floor division — partial apartments do not count.

    Args:
        pum_m2: Total usable area in m².
        avg_apartment_m2: Average apartment size (m²). Default 55 m² ≈ PL M3 standard.

    Returns:
        Estimated whole apartments. Always non-negative integer.

    Raises:
        ValueError: if pum_m2 is negative.
    """
    if pum_m2 < 0:
        raise ValueError(f"pum_m2 must be non-negative, got {pum_m2}")
    if avg_apartment_m2 <= 0:
        raise ValueError(f"avg_apartment_m2 must be positive, got {avg_apartment_m2}")
    return int(pum_m2 // avg_apartment_m2)


def compute_hash(rd: ReportData) -> str:
    """Compute deterministic 16-hex-char hash of input data (excludes timestamp).

    Used in PDF metadata so the architect can prove the report corresponds to
    a specific plot + MPZP parameter set, regardless of when it was generated.
    """
    payload = {
        "plot_id": rd.plot_id,
        "plot_address": rd.plot_address,
        "plot_area_m2": rd.plot_area_m2,
        "plot_polygon_wkt": rd.plot_polygon_wkt,
        "mpzp": asdict(rd.mpzp_summary),
        "setbacks": asdict(rd.setbacks),
        "indicators": [asdict(i) for i in rd.indicators],
        "verification": [asdict(v) for v in rd.verification_results],
        "variants": [asdict(v) for v in rd.buildup_variants],
        "pack_version": rd.pack_version,
        # generated_at NOT included — same data, different time = same hash
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return digest[:16]


GLOSSARY: Dict[str, str] = {
    "MPZP": (
        "Miejscowy Plan Zagospodarowania Przestrzennego — uchwała rady gminy "
        "określająca przeznaczenie terenu i zasady jego zabudowy."
    ),
    "WZ": (
        "Wskaźnik powierzchni Zabudowy. Stosunek powierzchni zabudowanej "
        "(rzut budynku na grunt) do powierzchni działki. Im wyższy, tym więcej "
        "ziemi pokryte budynkiem."
    ),
    "WIZ": (
        "Wskaźnik Intensywności Zabudowy. Stosunek sumy powierzchni wszystkich "
        "kondygnacji nadziemnych do powierzchni działki. WIZ 0.45 = 45% "
        "powierzchni działki sumarycznie w kondygnacjach."
    ),
    "PBC": (
        "Powierzchnia Biologicznie Czynna. Minimalny udział terenu pokrytego "
        "trawą, krzewami, drzewami lub przepuszczalną nawierzchnią — typowo "
        "30-40% działki w MN."
    ),
    "PUM": (
        "Powierzchnia Użytkowa Mieszkaniowa. Suma powierzchni użytkowych "
        "wszystkich mieszkań — bez ścian, klatek, korytarzy ogólnych."
    ),
    "linia zabudowy": (
        "Linia (wyznaczona w MPZP) określająca minimalną odległość elewacji "
        "budynku od granicy działki — typowo 6 m od drogi."
    ),
    "MN": "Zabudowa mieszkaniowa jednorodzinna.",
    "MW": "Zabudowa mieszkaniowa wielorodzinna.",
    "Klasa wysokości": (
        "Klasyfikacja WT: N (do 12 m), SW (12-25 m), W (25-55 m), WW (>55 m). "
        "Wpływa na wymagania ewakuacyjne, windy, klatki schodowe."
    ),
}
