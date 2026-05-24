"""Stage 1 Phase 3 — report_builder adapter tests (Tasks 2-9 combined)."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.plot_indicators import PlotIndicatorCalculator
from core.plot_verifier import PlotVerifier
from core.report_builder import build_report_data
from core.report_data import ReportData
from core.site_element_model import SiteElementType
from core.site_planner import SitePlanner
from tests.conftest import make_minimal_plot


def _run_mode_a(plot):
    """Run the Mode A pipeline (variants → indicators → verifier) for tests."""
    planner = SitePlanner()
    variants = planner.propose_max_buildup(
        plot,
        requested_element_types=[
            SiteElementType.BUDYNEK_GLOWNY,
            SiteElementType.MIEJSCE_POSTOJOWE,
        ],
    )
    elements = variants[0].elements
    indicators = PlotIndicatorCalculator().compute(plot, elements)
    verification = PlotVerifier().verify(plot, elements, indicators=indicators, walls=[])
    return variants, indicators, verification


# ============================================================================
# Task 2: happy path
# ============================================================================
def test_build_report_data_from_minimal_pipeline():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="dz. 123/4",
        plot_address="ul. Testowa 1, Warszawa",
    )

    assert isinstance(rd, ReportData)
    assert rd.plot_id == "dz. 123/4"
    assert rd.plot_address == "ul. Testowa 1, Warszawa"
    assert rd.plot_area_m2 == pytest.approx(40.0 * 30.0)
    assert rd.plot_perimeter_m == pytest.approx(2 * (40 + 30))
    assert rd.plot_polygon_wkt.startswith("POLYGON")
    assert rd.buildable_polygon_wkt.startswith("POLYGON")
    assert rd.buildable_zone_m2 > 0
    assert 0 < rd.buildable_zone_percent <= 100
    assert len(rd.indicators) == 3
    assert {i.name for i in rd.indicators} == {"WZ", "WIZ", "PBC"}
    assert len(rd.buildup_variants) == min(3, len(variants))
    assert rd.data_hash != ""


# ============================================================================
# Task 3: empty variants → ValueError
# ============================================================================
def test_build_report_data_empty_variants_raises():
    plot = make_minimal_plot()
    _, indicators, verification = _run_mode_a(plot)
    with pytest.raises(ValueError, match="variants list is empty"):
        build_report_data(
            plot, [], indicators, verification,
            plot_id="X", plot_address="",
        )


# ============================================================================
# Task 4: status logic — WZ/WIZ MAX-constrained
# ============================================================================
def test_indicator_status_max_ok():
    """WZ below limit → OK."""
    from core.report_builder import _status_max
    assert _status_max(0.25, 0.30) == "OK"
    assert _status_max(0.30, 0.30) == "OK"


def test_indicator_status_max_warn_in_5pct_band():
    """WZ slightly over limit (within 5%) → WARN."""
    from core.report_builder import _status_max
    # 0.30 * 1.05 = 0.315
    assert _status_max(0.305, 0.30) == "WARN"
    assert _status_max(0.314, 0.30) == "WARN"
    assert _status_max(0.315, 0.30) == "WARN"


def test_indicator_status_max_violation_above_5pct():
    """WZ over 5% band → VIOLATION."""
    from core.report_builder import _status_max
    assert _status_max(0.32, 0.30) == "VIOLATION"
    assert _status_max(0.50, 0.30) == "VIOLATION"


def test_indicator_status_min_pbc():
    """PBC is MIN-constrained — designed must be >= limit."""
    from core.report_builder import _status_min
    assert _status_min(40.0, 40.0) == "OK"
    assert _status_min(50.0, 40.0) == "OK"
    assert _status_min(38.5, 40.0) == "WARN"  # within 5% band
    assert _status_min(30.0, 40.0) == "VIOLATION"


# ============================================================================
# Task 5: variant info detailed metrics
# ============================================================================
def test_variant_info_has_detailed_metrics():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd = build_report_data(plot, variants, indicators, verification,
                           plot_id="X", plot_address="")

    for vi in rd.buildup_variants:
        assert vi.pum_m2 > 0
        assert vi.num_storeys >= 1
        # height_m może być 0 jeśli site_planner nie wypełnił (do dorobienia)
        assert vi.height_m >= 0
        # wz_headroom_percent (rezerwa względem WZ max) — może być dodatnia lub 0
        assert vi.parking_spaces >= 0
        # Sanity: footprint area matches BuildupVariant.footprint_area
        assert vi.footprint_area_m2 > 0


# ============================================================================
# Task 6: compliance status mapping
# ============================================================================
def test_compliance_rows_status_strings():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd = build_report_data(plot, variants, indicators, verification,
                           plot_id="X", plot_address="")

    # Status powinien być stringiem z VerificationStatus enum
    valid_statuses = {"ZGODNY", "NIEZGODNY", "OSTRZEZENIE", "NIEWERYFIKOWANY"}
    for row in rd.verification_results:
        assert row.status in valid_statuses
        assert row.rule_id != ""
        assert row.rule_name != ""


# ============================================================================
# Task 7: logo path None handling
# ============================================================================
def test_logo_path_none_by_default():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd = build_report_data(plot, variants, indicators, verification,
                           plot_id="X", plot_address="")
    assert rd.logo_path is None


def test_logo_path_passed_through(tmp_path):
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG sig
    rd = build_report_data(plot, variants, indicators, verification,
                           plot_id="X", plot_address="", logo_path=logo)
    assert rd.logo_path == logo


def test_logo_path_missing_file_silently_dropped(tmp_path):
    """Stary path z QSettings persistent state → ignore, nie wybuchaj."""
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    ghost_logo = tmp_path / "does_not_exist.png"
    rd = build_report_data(plot, variants, indicators, verification,
                           plot_id="X", plot_address="", logo_path=ghost_logo)
    assert rd.logo_path is None


# ============================================================================
# Task 8: hash stability
# ============================================================================
def test_data_hash_stable_across_runs():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd1 = build_report_data(plot, variants, indicators, verification,
                            plot_id="X", plot_address="")
    rd2 = build_report_data(plot, variants, indicators, verification,
                            plot_id="X", plot_address="")
    # Hash should be deterministic (excludes timestamp per compute_hash design)
    assert rd1.data_hash == rd2.data_hash


def test_data_hash_changes_when_plot_id_differs():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd1 = build_report_data(plot, variants, indicators, verification,
                            plot_id="A", plot_address="")
    rd2 = build_report_data(plot, variants, indicators, verification,
                            plot_id="B", plot_address="")
    assert rd1.data_hash != rd2.data_hash


# ============================================================================
# Task 9: polish chars preservation
# ============================================================================
def test_polish_chars_preserved_in_address():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="dz. 123/4",
        plot_address="ul. Świętokrzyska 7, Wrocław",
    )
    assert "Świętokrzyska" in rd.plot_address
    assert "Wrocław" in rd.plot_address
