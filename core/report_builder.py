"""Adapt Mode A pipeline outputs into a ReportData for PDF generation.

Phase 2 produced ReportData + the renderer/PDF stack. This module fills the
gap mentioned in core/report_data.py docstring ("from_pipeline") by mapping
real pipeline results onto a single ReportData instance.

Source-of-truth for field mappings: docs/superpowers/specs/
2026-05-13-stage1-phase3-ui-integration-design.md Sekcja 2.

Tasks 2-9 of docs/superpowers/plans/2026-05-14-stage1-phase3-ui-integration.md
all wired up:
  - happy path
  - empty variants → ValueError
  - status logic (Q14 5% band)
  - variant info detailed metrics
  - compliance mapping
  - logo path None handling
  - hash stability
  - polish chars preservation
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from core.plot_indicators import PlotIndicators, USABLE_AREA_FACTOR
from core.plot_model import BOUNDARY_SETBACK, BoundaryType, Plot
from core.plot_verifier import VerificationResult
from core.report_data import (
    ComplianceRow,
    IndicatorRow,
    MPZPSummary,
    ReportData,
    SetbackInfo,
    VariantInfo,
    compute_hash,
    estimate_units,
)
from core.site_element_model import SiteElementType
from core.site_planner import BuildupVariant


# Q14 5% warning band — see docs/OPEN_QUESTIONS.md Q14
WARN_BAND_PCT = 0.05


def _status_max(designed: float, limit: float) -> str:
    """Status for MAX-constrained indicator (WZ, WIZ).

    designed ≤ limit             → OK
    limit < designed ≤ 1.05*limit → WARN (Q14)
    designed > 1.05*limit        → VIOLATION
    """
    if designed <= limit:
        return "OK"
    if designed <= limit * (1 + WARN_BAND_PCT):
        return "WARN"
    return "VIOLATION"


def _status_min(designed: float, limit: float) -> str:
    """Status for MIN-constrained indicator (PBC).

    designed ≥ limit                 → OK
    limit > designed ≥ 0.95 * limit  → WARN (Q14)
    designed < 0.95 * limit          → VIOLATION
    """
    if designed >= limit:
        return "OK"
    if designed >= limit * (1 - WARN_BAND_PCT):
        return "WARN"
    return "VIOLATION"


def build_report_data(
    plot: Plot,
    variants: List[BuildupVariant],
    indicators: PlotIndicators,
    verification: List[VerificationResult],
    *,
    plot_id: str,
    plot_address: str,
    logo_path: Optional[Path] = None,
) -> ReportData:
    """Adapt Mode A pipeline outputs into a single ReportData.

    Args:
        plot: parent Plot z buildable_zone obliczonym.
        variants: BuildupVariant[] z site_planner.propose_max_buildup.
            MUST be non-empty.
        indicators: PlotIndicators z PlotIndicatorCalculator.
        verification: VerificationResult[] z PlotVerifier.
        plot_id: identyfikator z metadata dialog (np. "dz. 123/4").
        plot_address: opcjonalny adres (np. "ul. Testowa 1, Warszawa").
        logo_path: opcjonalna ścieżka do logo (white-label).

    Raises:
        ValueError: jeśli `variants` puste.
    """
    if not variants:
        raise ValueError(
            "build_report_data: variants list is empty — Mode A must produce "
            "at least one BuildupVariant before report can be generated."
        )

    # Defensywne: jesli logo_path nie istnieje na dysku (np. stary path z
    # QSettings persistent state) → ignoruj, nie blokuj generacji.
    if logo_path is not None and not Path(logo_path).exists():
        logo_path = None

    plot_area = plot.area
    buildable = plot.buildable_zone
    buildable_area = buildable.area if buildable is not None else 0.0
    buildable_percent = (buildable_area / plot_area * 100) if plot_area > 0 else 0.0
    buildable_wkt = buildable.wkt if buildable is not None else ""

    mpzp_summary = MPZPSummary(
        przeznaczenie=plot.mpzp.przeznaczenie,
        wz_max=plot.mpzp.max_wz,
        wiz_max=plot.mpzp.max_wiz,
        pbc_min_percent=plot.mpzp.min_pbc_percent,
        max_height_m=plot.mpzp.max_height,
        typ_zabudowy=plot.housing_type.value,
        line_zabudowy_m=plot.mpzp.setback_from_road,
        infrastructure_municipal=plot.mpzp.infrastructure_municipal,
    )

    neighbour_with_openings = BOUNDARY_SETBACK[BoundaryType.SASIAD_NIEZABUDOWANY][0]
    setbacks = SetbackInfo(
        front_m=plot.mpzp.setback_from_road,
        side_m=neighbour_with_openings,
        rear_m=neighbour_with_openings,
    )

    indicator_rows = [
        IndicatorRow(
            name="WZ",
            designed=indicators.wz_designed,
            limit=plot.mpzp.max_wz,
            unit="",
            status=_status_max(indicators.wz_designed, plot.mpzp.max_wz),
        ),
        IndicatorRow(
            name="WIZ",
            designed=indicators.wiz_designed,
            limit=plot.mpzp.max_wiz,
            unit="",
            status=_status_max(indicators.wiz_designed, plot.mpzp.max_wiz),
        ),
        IndicatorRow(
            name="PBC",
            designed=indicators.pbc_percent,
            limit=plot.mpzp.min_pbc_percent,
            unit="%",
            status=_status_min(indicators.pbc_percent, plot.mpzp.min_pbc_percent),
        ),
    ]

    compliance_rows = [
        ComplianceRow(
            rule_id=v.rule_id,
            rule_name=v.name,
            designed_value_str=v.designed_value_str,
            required_value_str=v.required_value_str,
            status=v.status.value,
            legal_basis=v.legal_basis,
        )
        for v in verification
    ]

    variant_infos = [_to_variant_info(v, plot) for v in variants[:3]]

    rd = ReportData(
        plot_id=plot_id,
        plot_address=plot_address,
        plot_area_m2=plot_area,
        plot_perimeter_m=plot.perimeter,
        plot_polygon_wkt=plot.geometry.wkt,
        buildable_polygon_wkt=buildable_wkt,
        mpzp_summary=mpzp_summary,
        buildable_zone_m2=buildable_area,
        buildable_zone_percent=buildable_percent,
        setbacks=setbacks,
        indicators=indicator_rows,
        verification_results=compliance_rows,
        buildup_variants=variant_infos,
        logo_path=logo_path,
    )
    rd.data_hash = compute_hash(rd)
    return rd


def build_report_data_mode_b(
    plot: Plot,
    subdivision_result,
    *,
    plot_id: str,
    plot_address: str,
    logo_path: Optional[Path] = None,
) -> ReportData:
    """Adapt Mode B (subdivision) outputs into ReportData.

    Mode B daje SubdivisionResult zawierający sub_plots[] + roads + nieuzytek.
    Mapujemy:
        - Plot głowny → mpzp summary + plot area
        - SubPlots → "buildup variants" (top 3 wg area buildable zone)
        - Indicators: wskazniki wykorzystania (zabudowa%, droga%, nieuzytek%)
        - Verification: errors/warnings z subdivision_result

    Args:
        plot: parent Plot.
        subdivision_result: SubdivisionResult z plot_subdivider.subdivide().
        plot_id: identifier (np. "dz. 123/4 — Mode B").
        plot_address: opcjonalny adres.
        logo_path: opcjonalne logo.

    Raises:
        ValueError jeśli subdivision_result.sub_plots puste.
    """
    if not subdivision_result.sub_plots:
        raise ValueError(
            "build_report_data_mode_b: sub_plots list is empty — "
            "subdivision must produce at least one sub-plot."
        )

    if logo_path is not None and not Path(logo_path).exists():
        logo_path = None

    plot_area = plot.area
    buildable = plot.buildable_zone
    buildable_area = buildable.area if buildable is not None else 0.0
    buildable_percent = (buildable_area / plot_area * 100) if plot_area > 0 else 0.0
    buildable_wkt = buildable.wkt if buildable is not None else ""

    mpzp_summary = MPZPSummary(
        przeznaczenie=plot.mpzp.przeznaczenie,
        wz_max=plot.mpzp.max_wz,
        wiz_max=plot.mpzp.max_wiz,
        pbc_min_percent=plot.mpzp.min_pbc_percent,
        max_height_m=plot.mpzp.max_height,
        typ_zabudowy=plot.housing_type.value,
        line_zabudowy_m=plot.mpzp.setback_from_road,
        infrastructure_municipal=plot.mpzp.infrastructure_municipal,
    )

    neighbour_with_openings = BOUNDARY_SETBACK[BoundaryType.SASIAD_NIEZABUDOWANY][0]
    setbacks = SetbackInfo(
        front_m=plot.mpzp.setback_from_road,
        side_m=neighbour_with_openings,
        rear_m=neighbour_with_openings,
    )

    # Indicators dla Mode B: wskazniki wykorzystania dzialki
    # (zamiast WZ/WIZ/PBC z Mode A — tutaj nie ma jeszcze budynkow)
    indicator_rows = [
        IndicatorRow(
            name="Zabudowa",
            designed=subdivision_result.buildable_area_percent,
            limit=plot.mpzp.max_wz * 100,
            unit="%",
            status="OK",
        ),
        IndicatorRow(
            name="Drogi wewn.",
            designed=subdivision_result.road_area_percent,
            limit=15.0,  # ~typowo do 15% optymalne
            unit="%",
            status=_status_max(subdivision_result.road_area_percent, 15.0),
        ),
        IndicatorRow(
            name="Nieuzytek",
            designed=subdivision_result.nieuzytek_percent,
            limit=10.0,  # ~typowo do 10% akceptowalne
            unit="%",
            status=_status_max(subdivision_result.nieuzytek_percent, 10.0),
        ),
    ]

    # Verification: errors + warnings z subdivision result
    compliance_rows = []
    for err in subdivision_result.validation_errors:
        compliance_rows.append(ComplianceRow(
            rule_id="SUBDIV-ERR",
            rule_name=err,
            designed_value_str="",
            required_value_str="",
            status="NIEZGODNY",
            legal_basis="",
        ))
    for warn in subdivision_result.validation_warnings:
        compliance_rows.append(ComplianceRow(
            rule_id="SUBDIV-WARN",
            rule_name=warn,
            designed_value_str="",
            required_value_str="",
            status="OSTRZEZENIE",
            legal_basis="",
        ))
    # Podsumowanie: jeśli brak errors — zgodny
    if not subdivision_result.validation_errors:
        compliance_rows.append(ComplianceRow(
            rule_id="SUBDIV-OK",
            rule_name=f"Podział na {len(subdivision_result.sub_plots)} pod-działek",
            designed_value_str=f"{subdivision_result.total_sub_area:.0f} m²",
            required_value_str=f"≥ {plot.mpzp.podzial.pow_dzialki_m2 if hasattr(plot.mpzp, 'podzial') else '?'} m² każda",
            status="ZGODNY",
            legal_basis="Q15 + Q16",
        ))

    # Variants: top 3 najwiekszych sub-dzialek (po buildable area)
    sorted_subs = sorted(
        subdivision_result.sub_plots,
        key=lambda s: -(s.buildable_zone.area if s.has_buildable_zone else 0),
    )
    variant_infos = []
    for i, sp in enumerate(sorted_subs[:3], 1):
        sp_buildable = sp.buildable_zone.area if sp.has_buildable_zone else 0.0
        sp_wz = sp_buildable / sp.area if sp.area > 0 else 0.0
        variant_infos.append(VariantInfo(
            number=i,
            footprint_area_m2=sp.area,
            wz=sp_wz,
            wiz=sp_wz,  # bez budynkow = WIZ == WZ
            pbc_percent=(1 - sp_wz) * 100,
            estimated_units=1,  # 1 dom/dzialka w Mode B
            description=f"Pod-działka {i}: {sp.area:.0f} m², strefa zabudowy {sp_buildable:.0f} m²",
            pum_m2=sp_buildable * USABLE_AREA_FACTOR,
            num_storeys=plot.mpzp.max_floors,
            height_m=plot.mpzp.max_height,
            wz_headroom_percent=max(0, (plot.mpzp.max_wz - sp_wz) * 100),
            pbc_headroom_percent=max(0, (1 - sp_wz) * 100 - plot.mpzp.min_pbc_percent),
            parking_spaces=int(plot.mpzp.parking_spaces_per_unit),
            long_description=f"Front działki: {sp.front_length:.1f} m. "
                             f"Dostęp do drogi: {'TAK' if sp.front_length > 0.5 else 'BRAK'}.",
        ))

    rd = ReportData(
        plot_id=plot_id,
        plot_address=plot_address,
        plot_area_m2=plot_area,
        plot_perimeter_m=plot.perimeter,
        plot_polygon_wkt=plot.geometry.wkt,
        buildable_polygon_wkt=buildable_wkt,
        mpzp_summary=mpzp_summary,
        buildable_zone_m2=buildable_area,
        buildable_zone_percent=buildable_percent,
        setbacks=setbacks,
        indicators=indicator_rows,
        verification_results=compliance_rows,
        buildup_variants=variant_infos,
        logo_path=logo_path,
    )
    rd.data_hash = compute_hash(rd)
    return rd


def _to_variant_info(v: BuildupVariant, plot: Plot) -> VariantInfo:
    """Map one BuildupVariant onto a VariantInfo with detailed metrics."""
    footprint = v.main_building.footprint_area
    floors = v.main_building.floors
    pum = footprint * floors * USABLE_AREA_FACTOR
    parking = sum(
        1 for e in v.elements if e.element_type == SiteElementType.MIEJSCE_POSTOJOWE
    )
    pbc_headroom = v.pbc_percent - plot.mpzp.min_pbc_percent

    return VariantInfo(
        number=v.number,
        footprint_area_m2=v.footprint_area,
        wz=v.wz,
        wiz=v.wiz,
        pbc_percent=v.pbc_percent,
        estimated_units=estimate_units(pum),
        description=v.description,
        pum_m2=pum,
        num_storeys=floors,
        height_m=v.main_building.height,
        wz_headroom_percent=v.wz_headroom_percent,
        pbc_headroom_percent=pbc_headroom,
        parking_spaces=parking,
        long_description=v.description,
    )
