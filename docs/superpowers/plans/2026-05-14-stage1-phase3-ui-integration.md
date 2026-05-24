# Stage 1 Phase 3 — UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Eksport raportu PDF" button to the Stage 1 tab in `ui/main_window.py` that, after Mode A runs successfully, opens a metadata dialog, lets the user pick a save path, and generates the existing 9-page PDF report using Phase 2 backend.

**Architecture:** A new adapter `core/report_builder.py` maps Mode A pipeline outputs (`Plot`, `BuildupVariant[]`, `PlotIndicators`, `VerificationResult[]`) onto a single `ReportData` (Phase 2 dataclass). A new dialog `ui/report_metadata_dialog.py` collects `plot_id`/`plot_address`/`logo_path` with `QSettings` persistence for the logo. `ui/stage1_window.py` caches Mode A results, gates the export button, and orchestrates the synchronous PDF generation with a busy state. The Phase 2 backend (`core/report_data.py`, `core/report_renderer.py`, `core/report_pdf.py`) is NOT modified.

**Tech Stack:** Python 3.13, PyQt5 5.15, shapely 2.1, reportlab + matplotlib (Phase 2), pytest, dataclasses, pathlib.

**Spec:** `docs/superpowers/specs/2026-05-13-stage1-phase3-ui-integration-design.md`

---

## File Structure

**Create:**
- `tests/conftest.py` — session-scoped `qapp` fixture, `isolated_qsettings` fixture, `_make_minimal_plot()` helper
- `core/report_builder.py` — `build_report_data()` adapter, `_status()`, `_to_variant_info()` helpers
- `ui/report_metadata_dialog.py` — `ReportMetadataDialog(QDialog)` with `get_metadata()` method
- `tests/test_report_builder.py` — 9 tests (happy path, empty variants, status band, headrooms, compliance, logo, hash, polish chars)
- `tests/test_report_metadata_dialog.py` — 5 tests (default plot_id, accept dict, cancel rejected, logo picker, QSettings)

**Modify:**
- `ui/stage1_window.py` — add `_mode_a_results` cache, `export_pdf_btn`, `_on_export_pdf()` handler, invalidation paths in `_run_mode_b` / `_build_plot` / `_on_housing_type_changed`
- `docs/STATE.md` — add Stage 1 Phase 3 completion section after Phase 2

**Do NOT touch:**
- `core/report_data.py`, `core/report_renderer.py`, `core/report_pdf.py` — Phase 2 backend frozen
- `tests/fixtures/sample_report.py` — Phase 2 fixture, reused only for reference

---

## Task 1: Test infrastructure (conftest fixtures + plot helper)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py` with session-scoped qapp, isolated_qsettings, and plot helper**

```python
"""Shared test fixtures for FloorPlan6.

- qapp: session-scoped QApplication for PyQt5 dialog tests.
- isolated_qsettings: redirects QSettings file storage to tmp_path so tests
  do not pollute the user's real ~/.config/FloorPlan6/Stage1Report.conf.
- make_minimal_plot: constructs a fully-populated Plot with buildable zone,
  used by Stage 1 Phase 3 report tests.
"""
from __future__ import annotations

import os
import sys

import pytest
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)


@pytest.fixture(scope="session")
def qapp():
    """Provide a session-scoped QApplication for PyQt5 dialog tests.

    Skipped in true headless environments where QApplication cannot construct.
    """
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PyQt5 not available")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else [""])
    yield app
    # Do NOT call app.quit() — session-scoped, other tests may need it.


@pytest.fixture
def isolated_qsettings(tmp_path, monkeypatch):
    """Redirect QSettings IniFormat UserScope to tmp_path so tests are isolated.

    Without this fixture, tests touching QSettings("FloorPlan6", "Stage1Report")
    would write to and read from the user's real config and pollute state across
    runs.
    """
    try:
        from PyQt5.QtCore import QSettings
    except ImportError:
        pytest.skip("PyQt5 not available")

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path),
    )
    yield tmp_path


def make_minimal_plot(
    width: float = 40.0,
    depth: float = 30.0,
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    infrastructure_municipal: bool = True,
) -> Plot:
    """Build a 40×30 m rectangular plot with 4 boundaries and computed buildable zone.

    Boundaries (clockwise from origin):
        0 (bottom)  DROGA
        1 (right)   SASIAD_ZABUDOWANY
        2 (top)     WLASNA
        3 (left)    SASIAD_NIEZABUDOWANY
    """
    poly = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
    coords = [(0, 0), (width, 0), (width, depth), (0, depth), (0, 0)]
    types = [
        BoundaryType.DROGA,
        BoundaryType.SASIAD_ZABUDOWANY,
        BoundaryType.WLASNA,
        BoundaryType.SASIAD_NIEZABUDOWANY,
    ]
    boundaries = [
        PlotBoundary(LineString([coords[i], coords[i + 1]]), types[i], i)
        for i in range(4)
    ]
    plot = Plot(
        number="P-test",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            max_wiz=0.60,
            min_pbc_percent=40.0,
            max_height=9.0,
            setback_from_road=5.0,
            max_floors=2,
            przeznaczenie="MN",
            parking_spaces_per_unit=2.0,
            infrastructure_municipal=infrastructure_municipal,
        ),
        housing_type=housing_type,
    )
    BuildableZoneBuilder().compute(plot)
    return plot
```

- [ ] **Step 2: Verify conftest imports clean and existing suite still green**

Run: `pytest tests/ --ignore=tests/test_gui.py -q 2>&1 | tail -5`
Expected: `196 passed` (Phase 2 baseline) or close — no regressions.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): add qapp, isolated_qsettings, make_minimal_plot fixtures

Prepares shared infrastructure for Stage 1 Phase 3 report builder + dialog tests.
Session-scoped QApplication avoids per-test construction cost; QSettings isolation
prevents tests polluting user real config."
```

---

## Task 2: `report_builder.py` happy path

**Files:**
- Create: `core/report_builder.py`
- Test: `tests/test_report_builder.py`

- [ ] **Step 1: Write the failing happy-path test**

Create `tests/test_report_builder.py`:

```python
"""Stage 1 Phase 3 — report_builder adapter tests."""
from __future__ import annotations

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
    verification = PlotVerifier().verify(plot, elements, walls=[])
    return variants, indicators, verification


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
    assert len(rd.buildup_variants) == len(variants[:3])
    assert rd.data_hash != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_builder.py::test_build_report_data_from_minimal_pipeline -v`
Expected: `ModuleNotFoundError: No module named 'core.report_builder'`

- [ ] **Step 3: Write minimal implementation**

Create `core/report_builder.py`:

```python
"""Adapt Mode A pipeline outputs into a ReportData for PDF generation.

Phase 2 produced ReportData + the renderer/PDF stack. This module fills the
gap mentioned in core/report_data.py docstring ("from_pipeline") by mapping
real pipeline results onto a single ReportData instance.

Source-of-truth for field mappings: docs/superpowers/specs/
2026-05-13-stage1-phase3-ui-integration-design.md Sekcja 2.
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

    Raises:
        ValueError: if variants is empty.
    """
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
            status="OK",  # placeholder, overwritten in Task 4
        ),
        IndicatorRow(
            name="WIZ",
            designed=indicators.wiz_designed,
            limit=plot.mpzp.max_wiz,
            unit="",
            status="OK",  # placeholder, overwritten in Task 4
        ),
        IndicatorRow(
            name="PBC",
            designed=indicators.pbc_percent,
            limit=plot.mpzp.min_pbc_percent,
            unit="%",
            status="OK",  # placeholder, overwritten in Task 4
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

    variant_infos = [
        _to_variant_info(v, plot) for v in variants[:3]
    ]

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_builder.py::test_build_report_data_from_minimal_pipeline -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add core/report_builder.py tests/test_report_builder.py
git commit -m "feat(report_builder): adapt Mode A pipeline → ReportData (happy path)

build_report_data() maps Plot/BuildupVariant[]/PlotIndicators/
VerificationResult[] onto Phase 2 ReportData. Mappings match field names from
core/report_data.py dataclass + Phase 2 fixture.

Indicator status logic still placeholder ('OK' for all) — added in next task."
```

---

## Task 3: Empty variants raises ValueError

**Files:**
- Modify: `core/report_builder.py` (add guard at top of `build_report_data`)
- Modify: `tests/test_report_builder.py` (add test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_report_builder.py`:

```python
def test_empty_variants_raises_valueerror():
    plot = make_minimal_plot()
    _, indicators, verification = _run_mode_a(plot)

    with pytest.raises(ValueError, match="variants must be non-empty"):
        build_report_data(
            plot, [], indicators, verification,
            plot_id="x", plot_address="y",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_builder.py::test_empty_variants_raises_valueerror -v`
Expected: FAIL — no ValueError raised (or unrelated `IndexError` later).

- [ ] **Step 3: Add the guard**

In `core/report_builder.py`, at the very top of `build_report_data` (right after the docstring):

```python
    if not variants:
        raise ValueError("variants must be non-empty (Mode A pipeline bug?)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_builder.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add core/report_builder.py tests/test_report_builder.py
git commit -m "feat(report_builder): raise ValueError when variants list is empty

Mode A without variants indicates upstream pipeline bug. Fail fast rather than
producing a PDF with no Wariant page."
```

---

## Task 4: Indicator status logic (Q14 5% band)

**Files:**
- Modify: `core/report_builder.py` (add `_status()` helper, wire to IndicatorRow construction)
- Modify: `tests/test_report_builder.py` (add test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_report_builder.py`:

```python
def test_indicator_status_OK_WARN_VIOLATION():
    """Q14 5% band: OK within limit, WARN within 5% over (max) or under (min),
    VIOLATION beyond."""
    from core.report_builder import _status

    # max-type (WZ/WIZ): designed should be <= limit
    assert _status(0.25, 0.30, is_min=False) == "OK"        # under limit
    assert _status(0.30, 0.30, is_min=False) == "OK"        # exactly at limit
    assert _status(0.31, 0.30, is_min=False) == "WARN"      # 0.30 + 5% = 0.315
    assert _status(0.316, 0.30, is_min=False) == "VIOLATION"

    # min-type (PBC): designed should be >= limit
    assert _status(45.0, 40.0, is_min=True) == "OK"         # over limit
    assert _status(40.0, 40.0, is_min=True) == "OK"         # exactly at limit
    assert _status(39.0, 40.0, is_min=True) == "WARN"       # 40 - 5% = 38.0
    assert _status(37.0, 40.0, is_min=True) == "VIOLATION"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_builder.py::test_indicator_status_OK_WARN_VIOLATION -v`
Expected: FAIL — `ImportError: cannot import name '_status'`

- [ ] **Step 3: Add `_status()` helper and wire it**

Add to `core/report_builder.py` after `_to_variant_info`:

```python
def _status(designed: float, limit: float, *, is_min: bool) -> str:
    """Compute OK/WARN/VIOLATION with Q14 5%-of-limit warning band.

    Args:
        designed: actual computed value.
        limit: MPZP/WT limit.
        is_min: True for "designed must be ≥ limit" (PBC); False for "≤" (WZ/WIZ).
    """
    band = limit * 0.05
    if is_min:
        if designed >= limit:
            return "OK"
        if designed >= limit - band:
            return "WARN"
        return "VIOLATION"
    else:
        if designed <= limit:
            return "OK"
        if designed <= limit + band:
            return "WARN"
        return "VIOLATION"
```

Then in `build_report_data`, replace the three `status="OK"  # placeholder` literals with calls to `_status`:

```python
    indicator_rows = [
        IndicatorRow(
            name="WZ",
            designed=indicators.wz_designed,
            limit=plot.mpzp.max_wz,
            unit="",
            status=_status(indicators.wz_designed, plot.mpzp.max_wz, is_min=False),
        ),
        IndicatorRow(
            name="WIZ",
            designed=indicators.wiz_designed,
            limit=plot.mpzp.max_wiz,
            unit="",
            status=_status(indicators.wiz_designed, plot.mpzp.max_wiz, is_min=False),
        ),
        IndicatorRow(
            name="PBC",
            designed=indicators.pbc_percent,
            limit=plot.mpzp.min_pbc_percent,
            unit="%",
            status=_status(indicators.pbc_percent, plot.mpzp.min_pbc_percent, is_min=True),
        ),
    ]
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_report_builder.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add core/report_builder.py tests/test_report_builder.py
git commit -m "feat(report_builder): Q14 5% band status logic for indicators

OK / WARN (within 5% of limit) / VIOLATION (over band) for WZ, WIZ (max) and
PBC (min). Matches Q14 decision from 2026-05-07."
```

---

## Task 5: Variant info detailed metrics (headrooms, PUM, units, parking)

**Files:**
- Modify: `tests/test_report_builder.py` (add test)
- Already implemented in Task 2 — this task only adds a regression test.

- [ ] **Step 1: Add the test**

Append to `tests/test_report_builder.py`:

```python
def test_variant_info_headroom_computed():
    """VariantInfo carries wz_headroom_percent, pbc_headroom_percent, estimated_units,
    pum_m2, num_storeys, height_m, parking_spaces — populated from BuildupVariant +
    Plot.mpzp + element list."""
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
    )

    for vi, v in zip(rd.buildup_variants, variants[:3]):
        # Mapped from BuildupVariant directly
        assert vi.wz == v.wz
        assert vi.wz_headroom_percent == v.wz_headroom_percent
        # Computed in adapter
        assert vi.pbc_headroom_percent == pytest.approx(
            v.pbc_percent - plot.mpzp.min_pbc_percent
        )
        # Derived from main_building
        assert vi.num_storeys == v.main_building.floors
        assert vi.height_m == v.main_building.height
        assert vi.pum_m2 > 0
        assert vi.estimated_units >= 0
        # parking_spaces equals number of MIEJSCE_POSTOJOWE in v.elements
        from core.site_element_model import SiteElementType
        expected_parking = sum(
            1 for e in v.elements if e.element_type == SiteElementType.MIEJSCE_POSTOJOWE
        )
        assert vi.parking_spaces == expected_parking
        # long_description reuses BuildupVariant.description (decision 2026-05-14)
        assert vi.long_description == v.description
```

- [ ] **Step 2: Run test to verify it passes (implementation already done in Task 2)**

Run: `pytest tests/test_report_builder.py::test_variant_info_headroom_computed -v`
Expected: `1 passed`

If it fails, the existing `_to_variant_info` implementation has a bug — fix per the test assertions before committing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_builder.py
git commit -m "test(report_builder): regression for VariantInfo detailed metrics

Locks in headrooms, PUM derivation, parking count, num_storeys/height_m from
main_building, and long_description reuse of v.description."
```

---

## Task 6: Compliance status mapping

**Files:**
- Modify: `tests/test_report_builder.py` (add test)
- Already implemented in Task 2.

- [ ] **Step 1: Add the test**

Append to `tests/test_report_builder.py`:

```python
def test_compliance_status_mapping():
    """VerificationStatus enum values map verbatim to ComplianceRow.status string."""
    from core.plot_verifier import VerificationResult, VerificationStatus

    plot = make_minimal_plot()
    variants, indicators, _ = _run_mode_a(plot)

    verification = [
        VerificationResult(
            rule_id="wt_001", name="Test rule",
            status=VerificationStatus.ZGODNY,
            designed_value_str="6 m", required_value_str="≥ 3 m",
            legal_basis="§ 12",
        ),
        VerificationResult(
            rule_id="wt_002", name="Test rule 2",
            status=VerificationStatus.NIEZGODNY,
            designed_value_str="2 m", required_value_str="≥ 3 m",
            legal_basis="§ 12",
        ),
    ]

    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
    )

    assert len(rd.verification_results) == 2
    assert rd.verification_results[0].rule_id == "wt_001"
    assert rd.verification_results[0].rule_name == "Test rule"
    assert rd.verification_results[0].status == "ZGODNY"
    assert rd.verification_results[1].status == "NIEZGODNY"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_report_builder.py::test_compliance_status_mapping -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_builder.py
git commit -m "test(report_builder): regression for VerificationResult → ComplianceRow mapping

Confirms VerificationResult.name → ComplianceRow.rule_name (field rename),
and VerificationStatus enum .value → status string verbatim."
```

---

## Task 7: Logo path None handling

**Files:**
- Modify: `tests/test_report_builder.py` (add 2 tests)
- Already implemented in Task 2.

- [ ] **Step 1: Add both tests**

Append to `tests/test_report_builder.py`:

```python
def test_logo_path_None_does_not_crash():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)
    # No logo_path arg = default None
    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
    )
    assert rd is not None


def test_logo_path_None_propagates():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
        logo_path=None,
    )

    # logo_path is a top-level field on ReportData (not in a 'cover' sub-object)
    assert rd.logo_path is None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_report_builder.py -v -k "logo"`
Expected: `2 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_builder.py
git commit -m "test(report_builder): logo_path=None propagates to ReportData.logo_path"
```

---

## Task 8: Hash stability

**Files:**
- Modify: `tests/test_report_builder.py` (add test)
- Already implemented in Task 2 (`rd.data_hash = compute_hash(rd)` at end).

- [ ] **Step 1: Add the test**

Append to `tests/test_report_builder.py`:

```python
def test_hash_stable_for_same_inputs():
    """Same Plot + variants + indicators + verification → same data_hash,
    independent of generated_at timestamp."""
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd1 = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
    )
    rd2 = build_report_data(
        plot, variants, indicators, verification,
        plot_id="x", plot_address="y",
    )
    assert rd1.data_hash == rd2.data_hash
    assert len(rd1.data_hash) == 16  # 16 hex chars per compute_hash contract


def test_hash_changes_when_plot_id_changes():
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd1 = build_report_data(
        plot, variants, indicators, verification,
        plot_id="dz. 1/1", plot_address="y",
    )
    rd2 = build_report_data(
        plot, variants, indicators, verification,
        plot_id="dz. 2/2", plot_address="y",
    )
    assert rd1.data_hash != rd2.data_hash
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_report_builder.py -v -k "hash"`
Expected: `2 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_builder.py
git commit -m "test(report_builder): data_hash stable across calls, varies with plot_id

compute_hash excludes generated_at by design; same data => same hash."
```

---

## Task 9: Polish chars preservation

**Files:**
- Modify: `tests/test_report_builder.py` (add test)
- Already implemented in Task 2 (str args pass-through).

- [ ] **Step 1: Add the test**

Append to `tests/test_report_builder.py`:

```python
def test_polish_chars_preserved():
    """Polish diacritics in plot_address survive the adapter into rd.plot_address."""
    plot = make_minimal_plot()
    variants, indicators, verification = _run_mode_a(plot)

    rd = build_report_data(
        plot, variants, indicators, verification,
        plot_id="Działka ąęćźż",
        plot_address="ul. Słoneczna 12, Warszawa-Włochy",
    )

    assert rd.plot_id == "Działka ąęćźż"
    assert "Słoneczna" in rd.plot_address
    assert "Włochy" in rd.plot_address
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_report_builder.py::test_polish_chars_preserved -v`
Expected: `1 passed`

- [ ] **Step 3: Run full builder suite + full suite for regression check**

Run: `pytest tests/test_report_builder.py -v`
Expected: `10 passed` (1+1+1+1+1+2+2+1+1 = should be ~10)

Run: `pytest tests/ --ignore=tests/test_gui.py -q 2>&1 | tail -3`
Expected: previous count + new tests, no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_report_builder.py
git commit -m "test(report_builder): Polish diacritics preserved end-to-end in plot_id/address"
```

---

## Task 10: `ReportMetadataDialog` skeleton + default plot_id

**Files:**
- Create: `ui/report_metadata_dialog.py`
- Create: `tests/test_report_metadata_dialog.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_report_metadata_dialog.py`:

```python
"""Stage 1 Phase 3 — ReportMetadataDialog tests.

All tests use session-scoped qapp fixture from conftest.py.
"""
from __future__ import annotations

from datetime import date

import pytest


def test_dialog_default_plot_id_is_today(qapp, isolated_qsettings):
    from ui.report_metadata_dialog import ReportMetadataDialog

    default_pid = f"Działka {date.today():%Y-%m-%d}"
    dlg = ReportMetadataDialog(default_plot_id=default_pid)
    assert dlg.plot_id_edit.text() == default_pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_metadata_dialog.py::test_dialog_default_plot_id_is_today -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the dialog**

Create `ui/report_metadata_dialog.py`:

```python
"""Pre-save metadata dialog for Stage 1 PDF report export.

Collects:
    - plot_id (string, required)
    - plot_address (string, required)
    - logo_path (Path | None, persisted via QSettings)

After construction, caller invokes exec_() and checks the return value:
    Accepted → get_metadata() returns dict
    Rejected → get_metadata() should not be called
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

QSETTINGS_ORG = "FloorPlan6"
QSETTINGS_APP = "Stage1Report"
QSETTINGS_LAST_LOGO_KEY = "last_logo_path"


class ReportMetadataDialog(QDialog):
    """Collect plot_id, plot_address, optional logo_path before PDF save."""

    def __init__(self, parent=None, default_plot_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Dane raportu")

        self.plot_id_edit = QLineEdit(default_plot_id)
        self.plot_id_edit.setPlaceholderText("np. dz. 123/4, obręb 7-08-12")

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("ul. Słoneczna 12, Warszawa")

        self._logo_path: Optional[Path] = None
        self.logo_path_lbl = QLabel("(brak)")
        self.logo_btn = QPushButton("Wybierz logo…")
        self.logo_btn.clicked.connect(self._on_pick_logo)

        # Restore last-used logo
        s = QSettings(QSETTINGS_ORG, QSETTINGS_APP)
        last = s.value(QSETTINGS_LAST_LOGO_KEY, "", type=str)
        if last and Path(last).exists():
            self._logo_path = Path(last)
            self.logo_path_lbl.setText(os.path.basename(last))

        form = QFormLayout()
        form.addRow("Identyfikator działki:", self.plot_id_edit)
        form.addRow("Adres działki:", self.address_edit)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_btn)
        logo_row.addWidget(self.logo_path_lbl, stretch=1)
        form.addRow("Logo (opcjonalne):", logo_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _on_pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz logo",
            "",
            "Obrazy (*.png *.jpg *.jpeg)",
        )
        if path:
            self._logo_path = Path(path)
            self.logo_path_lbl.setText(os.path.basename(path))

    def _on_accept(self):
        # Persist last-used logo so next run pre-fills it
        if self._logo_path is not None:
            s = QSettings(QSETTINGS_ORG, QSETTINGS_APP)
            s.setValue(QSETTINGS_LAST_LOGO_KEY, str(self._logo_path))
        self.accept()

    def get_metadata(self) -> dict:
        """Return metadata dict. Caller MUST check exec_() == Accepted first."""
        return {
            "plot_id": self.plot_id_edit.text(),
            "plot_address": self.address_edit.text(),
            "logo_path": self._logo_path,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_metadata_dialog.py::test_dialog_default_plot_id_is_today -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add ui/report_metadata_dialog.py tests/test_report_metadata_dialog.py
git commit -m "feat(ui): ReportMetadataDialog skeleton with QSettings logo persistence

Pre-save dialog for Stage 1 PDF export collecting plot_id, address, optional
logo. QSettings(\"FloorPlan6\", \"Stage1Report\") remembers last used logo
across sessions."
```

---

## Task 11: Dialog accept returns metadata dict

**Files:**
- Modify: `tests/test_report_metadata_dialog.py`

- [ ] **Step 1: Add test**

Append to `tests/test_report_metadata_dialog.py`:

```python
def test_dialog_accept_returns_metadata_dict(qapp, isolated_qsettings):
    from ui.report_metadata_dialog import ReportMetadataDialog

    dlg = ReportMetadataDialog(default_plot_id="dz. 1/1")
    dlg.plot_id_edit.setText("dz. 99/9")
    dlg.address_edit.setText("ul. Przykładowa 1")

    # Simulate Accept without actually exec_()ing (would block the test).
    dlg._on_accept()

    meta = dlg.get_metadata()
    assert isinstance(meta, dict)
    assert set(meta.keys()) == {"plot_id", "plot_address", "logo_path"}
    assert meta["plot_id"] == "dz. 99/9"
    assert meta["plot_address"] == "ul. Przykładowa 1"
    assert meta["logo_path"] is None
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_report_metadata_dialog.py::test_dialog_accept_returns_metadata_dict -v`
Expected: `1 passed` (impl already present)

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_metadata_dialog.py
git commit -m "test(metadata_dialog): get_metadata returns dict with 3 keys after accept"
```

---

## Task 12: Dialog cancel returns rejected

**Files:**
- Modify: `tests/test_report_metadata_dialog.py`

- [ ] **Step 1: Add test**

Append to `tests/test_report_metadata_dialog.py`:

```python
def test_dialog_cancel_returns_rejected(qapp, isolated_qsettings):
    """Cancel triggers reject() — exec_() would return QDialog.Rejected.

    We don't actually exec_() (it blocks). We just verify that calling reject()
    sets result() to QDialog.Rejected and that user-typed values are still
    accessible (caller must NOT call get_metadata after reject anyway)."""
    from PyQt5.QtWidgets import QDialog
    from ui.report_metadata_dialog import ReportMetadataDialog

    dlg = ReportMetadataDialog(default_plot_id="dz. 1/1")
    dlg.reject()
    assert dlg.result() == QDialog.Rejected
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_report_metadata_dialog.py::test_dialog_cancel_returns_rejected -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_metadata_dialog.py
git commit -m "test(metadata_dialog): cancel triggers QDialog.Rejected"
```

---

## Task 13: Logo picker updates label

**Files:**
- Modify: `tests/test_report_metadata_dialog.py`

- [ ] **Step 1: Add test**

Append to `tests/test_report_metadata_dialog.py`:

```python
def test_logo_picker_updates_label(qapp, isolated_qsettings, tmp_path, monkeypatch):
    """Selecting a logo file updates the visible label to the basename and
    stores Path on the dialog."""
    from pathlib import Path
    from PyQt5.QtWidgets import QFileDialog
    from ui.report_metadata_dialog import ReportMetadataDialog

    fake_logo = tmp_path / "my_studio_logo.png"
    fake_logo.write_bytes(b"\x89PNG\r\n\x1a\n")

    # Monkeypatch the open dialog to return our fake path without showing GUI.
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **kw: (str(fake_logo), "Obrazy (*.png *.jpg *.jpeg)")),
    )

    dlg = ReportMetadataDialog()
    assert dlg.logo_path_lbl.text() == "(brak)"

    dlg._on_pick_logo()

    assert dlg._logo_path == Path(str(fake_logo))
    assert dlg.logo_path_lbl.text() == "my_studio_logo.png"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_report_metadata_dialog.py::test_logo_picker_updates_label -v`
Expected: `1 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_metadata_dialog.py
git commit -m "test(metadata_dialog): logo picker stores Path and updates basename label"
```

---

## Task 14: QSettings remembers last logo across instances

**Files:**
- Modify: `tests/test_report_metadata_dialog.py`

- [ ] **Step 1: Add test**

Append to `tests/test_report_metadata_dialog.py`:

```python
def test_qsettings_remembers_last_logo(qapp, isolated_qsettings, tmp_path):
    """First dialog accepts with a logo path; a second dialog should restore it.

    Isolation is provided by the isolated_qsettings fixture (writes go to
    tmp_path/FloorPlan6/Stage1Report.ini, not the user's real config)."""
    from pathlib import Path
    from ui.report_metadata_dialog import ReportMetadataDialog

    fake_logo = tmp_path / "company_logo.png"
    fake_logo.write_bytes(b"\x89PNG\r\n\x1a\n")

    dlg1 = ReportMetadataDialog()
    dlg1._logo_path = Path(str(fake_logo))
    dlg1._on_accept()

    dlg2 = ReportMetadataDialog()
    assert dlg2._logo_path == Path(str(fake_logo))
    assert dlg2.logo_path_lbl.text() == "company_logo.png"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_report_metadata_dialog.py::test_qsettings_remembers_last_logo -v`
Expected: `1 passed`

- [ ] **Step 3: Run full dialog suite**

Run: `pytest tests/test_report_metadata_dialog.py -v`
Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
git add tests/test_report_metadata_dialog.py
git commit -m "test(metadata_dialog): QSettings restores last-used logo across instances

Uses isolated_qsettings fixture so writes go to tmp_path and do not pollute
the user's real ~/.config/FloorPlan6/Stage1Report.conf."
```

---

## Task 15: Stage1Window — cache attribute + export button (disabled)

**Files:**
- Modify: `ui/stage1_window.py`

- [ ] **Step 1: Read current `Stage1Widget.__init__` and locate `generate_btn`**

Run: `grep -n "generate_btn\|self\.mode_a_results\|def __init__\|class Stage1Widget" ui/stage1_window.py`

Note line numbers — you'll insert the new cache attr after the existing attributes and add the new button right after `generate_btn` in its layout.

- [ ] **Step 2: Add cache attribute**

In `Stage1Widget.__init__`, near other instance attributes (e.g., near `self._current_plot = None` or similar), add:

```python
        # Phase 3: cache of Mode A pipeline results for PDF export.
        # Tuple shape: (plot, variants, indicators, verification) | None
        self._mode_a_results = None
```

- [ ] **Step 3: Add export button under Generate button**

Locate the line that adds `self.generate_btn` to a layout. Right after it, add:

```python
        self.export_pdf_btn = QPushButton("📄 Eksport raportu PDF")
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setToolTip(
            "Wygeneruj raport po uruchomieniu Generate (Mode A)."
        )
        self.export_pdf_btn.setStyleSheet(
            "QPushButton:enabled { background-color: #27AE60; color: white; "
            "font-weight: bold; padding: 6px; }"
        )
        self.export_pdf_btn.clicked.connect(self._on_export_pdf)
        # Add to the same layout `generate_btn` was added to (replace `layout`
        # with the actual variable name if different):
        layout.addWidget(self.export_pdf_btn)
```

Add a stub method at the bottom of the class:

```python
    def _on_export_pdf(self):
        """Handler implemented in Task 17."""
        pass
```

Make sure `QPushButton` is in the existing PyQt5 imports at the top of the file. If `QPushButton` isn't already imported, add it to the `from PyQt5.QtWidgets import (...)` line.

- [ ] **Step 4: Smoke check — app still launches**

Run: `PYTHONPATH=. python -c "from ui.stage1_window import Stage1Widget; print('import OK')"`
Expected: `import OK` (no exceptions).

- [ ] **Step 5: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1_window): add _mode_a_results cache + disabled export_pdf_btn

Button placed under Generate, disabled until Mode A succeeds. Handler stub —
implementation follows in next task."
```

---

## Task 16: Stage1Window — _run_mode_a populates cache + enables button

**Files:**
- Modify: `ui/stage1_window.py`

- [ ] **Step 1: Locate `_run_mode_a` method**

Run: `grep -n "def _run_mode_a\|def _render_mode_a\|def _show_mode_a_info" ui/stage1_window.py`

The method runs `SitePlanner.propose_max_buildup`, then computes indicators, then runs verifier. You'll add cache population at the end of the success path.

- [ ] **Step 2: At the end of `_run_mode_a`'s success path, set the cache and enable the button**

Inside `_run_mode_a`, just before the method returns (after `_render_mode_a` / `_show_mode_a_info` are called), add:

```python
        # Phase 3: store pipeline results so PDF export can reuse them.
        self._mode_a_results = (plot, variants, indicators, verification)
        self.export_pdf_btn.setEnabled(True)
        self.export_pdf_btn.setToolTip("Generuj 9-stronicowy raport PDF dla tej działki.")
```

Use the same variable names that exist in `_run_mode_a` — adapt `plot`, `variants`, `indicators`, `verification` to the actual names if they differ.

- [ ] **Step 3: Smoke check — import still works**

Run: `PYTHONPATH=. python -c "from ui.stage1_window import Stage1Widget; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1_window): _run_mode_a caches pipeline results and enables export button

After a successful Mode A run, (plot, variants, indicators, verification) is
stored in self._mode_a_results and the export PDF button is enabled with an
updated tooltip."
```

---

## Task 17: Stage1Window — _on_export_pdf full handler

**Files:**
- Modify: `ui/stage1_window.py`

- [ ] **Step 1: Add required imports at the top of `ui/stage1_window.py`**

Add (or merge into existing) imports:

```python
import re
from datetime import date

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)

from core.report_builder import build_report_data
from core.report_pdf import generate_pdf
from ui.report_metadata_dialog import ReportMetadataDialog
```

Only add what isn't already imported — don't duplicate.

- [ ] **Step 2: Replace the `_on_export_pdf` stub with the full handler**

Replace the stub:

```python
    def _on_export_pdf(self):
        """Generate a 9-page PDF report from cached Mode A results.

        Flow:
            1. Guard: cache None → warning + return (defensive).
            2. ReportMetadataDialog → collect plot_id / address / logo.
            3. QFileDialog → pick save path with prefilled filename.
            4. Busy state: cursor + disabled button + processEvents.
            5. build_report_data + generate_pdf inside try/except.
            6. Success: QMessageBox with "Open" option → launch via QDesktopServices.
        """
        # E1: defensive guard
        if self._mode_a_results is None:
            QMessageBox.warning(
                self,
                "Brak danych",
                "Najpierw uruchom Generate (Mode A), żeby przygotować dane raportu.",
            )
            return

        # Collect metadata
        today = date.today()
        default_pid = f"Działka {today:%Y-%m-%d}"
        dlg = ReportMetadataDialog(self, default_plot_id=default_pid)
        if dlg.exec_() != ReportMetadataDialog.Accepted:
            return  # E2 — cancel
        meta = dlg.get_metadata()

        # Pick save path
        suggested = f"Raport_{meta['plot_id']}_{today:%Y-%m-%d}.pdf"
        suggested = re.sub(r"[^\w\-_. ]", "_", suggested)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz raport PDF",
            suggested,
            "PDF (*.pdf)",
        )
        if not path:
            return  # E3 — cancel save

        # Busy state
        original_text = self.export_pdf_btn.text()
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setText("Generuję raport…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        statusbar = self.window().statusBar() if hasattr(self.window(), "statusBar") else None
        if statusbar:
            statusbar.showMessage("Generowanie PDF…")
        QApplication.processEvents()

        try:
            plot, variants, indicators, verification = self._mode_a_results
            rd = build_report_data(
                plot, variants, indicators, verification,
                plot_id=meta["plot_id"],
                plot_address=meta["plot_address"],
                logo_path=meta["logo_path"],
            )
            generate_pdf(rd, path)
        except Exception as e:
            # E4 / E5 / E6
            QMessageBox.critical(
                self,
                "Błąd generacji",
                f"Nie udało się wygenerować PDF:\n{e}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.export_pdf_btn.setEnabled(True)
            self.export_pdf_btn.setText(original_text)

        # Success
        if statusbar:
            statusbar.showMessage(f"Raport zapisany: {path}", 5000)
        resp = QMessageBox.information(
            self,
            "Raport gotowy",
            f"PDF zapisany:\n{path}",
            QMessageBox.Open | QMessageBox.Ok,
        )
        if resp == QMessageBox.Open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
```

- [ ] **Step 3: Verify the import still works**

Run: `PYTHONPATH=. python -c "from ui.stage1_window import Stage1Widget; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1_window): _on_export_pdf full handler with busy state

Implements Sekcja 3 of the Phase 3 spec end-to-end:
  - Defensive cache guard (E1)
  - Metadata dialog + cancel (E2)
  - QFileDialog with sanitized filename + cancel (E3)
  - Busy state: wait cursor, disabled button, processEvents
  - build_report_data + generate_pdf inside try/except (E4-E6)
  - Success: status bar message + 'Open PDF' option via QDesktopServices"
```

---

## Task 18: Cache invalidation on Mode B, build failures, housing-type toggle

**Files:**
- Modify: `ui/stage1_window.py`

- [ ] **Step 1: Locate invalidation points**

Run: `grep -n "def _run_mode_b\|def _build_plot\|def _on_housing_type_changed\|housing_type.*changed\|housing_type.*toggled" ui/stage1_window.py`

You'll inject the same cache-invalidation snippet at:
  - The start of `_run_mode_b` (running Mode B means user is no longer on Mode A results).
  - Each failure path in `_build_plot` (where the method returns early without producing a plot).
  - The handler triggered by toggling the housing type radio buttons (often `_on_housing_type_changed` or a lambda bound to `toggled.connect`).

- [ ] **Step 2: Extract a helper method**

Add to `Stage1Widget`:

```python
    def _invalidate_export_cache(self):
        """Clear Mode A cache and disable export button.

        Called when results would no longer match what's on screen:
          - User runs Mode B (different mode).
          - _build_plot fails (no valid plot to report on).
          - Housing type toggle (would re-run pipeline).
        """
        self._mode_a_results = None
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.setToolTip(
            "Wygeneruj raport po uruchomieniu Generate (Mode A)."
        )
```

- [ ] **Step 3: Call the helper at each invalidation point**

At the start of `_run_mode_b`:

```python
        self._invalidate_export_cache()
```

In every early-return path of `_build_plot` (failure paths — typically lines where the method shows a warning and returns `None`):

```python
        self._invalidate_export_cache()
        return None
```

In the housing-type toggle handler (or lambda):

```python
        self._invalidate_export_cache()
```

- [ ] **Step 4: Smoke check**

Run: `PYTHONPATH=. python -c "from ui.stage1_window import Stage1Widget; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add ui/stage1_window.py
git commit -m "feat(stage1_window): invalidate export cache on Mode B / build fail / housing toggle

_invalidate_export_cache() helper clears _mode_a_results and disables the
export button. Called at start of _run_mode_b, in each _build_plot failure
return, and on housing-type radio toggle. Prevents PDF generated from
out-of-date pipeline results."
```

---

## Task 19: Run full test suite + manual smoke + update STATE.md

**Files:**
- Modify: `docs/STATE.md`

- [ ] **Step 1: Run report-related tests**

Run: `pytest tests/test_report_builder.py tests/test_report_metadata_dialog.py -v 2>&1 | tail -30`
Expected: `~15 passed` (10 builder + 5 dialog). All green.

- [ ] **Step 2: Run full non-GUI suite, verify no regressions**

Run: `pytest tests/ --ignore=tests/test_gui.py -q 2>&1 | tail -3`
Expected: prior baseline (196) + new tests (~14-15) = ~210 passed, ~30 skipped, 0 failed.

- [ ] **Step 3: Manual smoke verification (B8 — verify before "done")**

Cannot be automated; run by hand:

```bash
PYTHONPATH=. python ui/main_window.py
```

Walk through this checklist:

1. Open the Stage 1 tab.
2. Load a plot (manual outline or from ArchiCAD).
3. Choose Mode A. Click **Generate**.
4. Verify: "📄 Eksport raportu PDF" button under Generate becomes enabled (green).
5. Click Eksport. The "Dane raportu" dialog appears with default plot_id "Działka YYYY-MM-DD".
6. Type Polish chars: plot_id `Działka ąęćźż`, address `ul. Słoneczna 12, Włochy`.
7. (Optional) Pick a logo file. Verify label shows basename.
8. Click OK. The QFileDialog appears with prefilled filename (Polish chars sanitized to `_` is acceptable).
9. Pick a save location. Click Save.
10. Verify: wait cursor appears briefly, button shows "Generuję raport…", status bar updates.
11. Verify: "Raport gotowy" message box appears. Click "Open".
12. The PDF opens in the default viewer. Verify:
    - 9 pages render.
    - Polish chars `Słoneczna`, `Włochy`, `Działka` look correct.
    - Logo (if picked) appears on cover + footer.
    - Variant page shows headroom percentages and parking spaces.
13. Close the PDF. Back in the app, switch to Mode B and run it. Verify: Eksport button becomes disabled with tooltip about Mode A.
14. Switch back to Mode A and re-run Generate. Verify: button re-enables.

If any step fails, fix the underlying issue (don't paper over with try/except).

- [ ] **Step 4: Update `docs/STATE.md`**

Locate the Stage 1 Phase 3 section (currently marked "BRAINSTORMED 2026-05-13, NOT IMPLEMENTED"). Replace it with:

```markdown
### Stage 1 — Phase 3 (UI Integration) — COMPLETED 2026-05-14

| Component | Status |
|---|---|
| `core/report_builder.py` | ✅ `build_report_data` adapter (Mode A pipeline → ReportData) + `_status` (Q14 band) + `_to_variant_info` (headrooms, PUM, parking) |
| `ui/report_metadata_dialog.py` | ✅ `ReportMetadataDialog` pre-save metadata dialog with QSettings logo persistence |
| `ui/stage1_window.py` | ✅ `_mode_a_results` cache + `export_pdf_btn` + `_on_export_pdf` handler + `_invalidate_export_cache` |
| `tests/conftest.py` | ✅ session-scoped `qapp` fixture + `isolated_qsettings` fixture + `make_minimal_plot` helper |
| `tests/test_report_builder.py` | ✅ 10 tests pass (happy path, empty variants → ValueError, Q14 status, variant headrooms, compliance mapping, logo None, hash stability/variability, polish chars) |
| `tests/test_report_metadata_dialog.py` | ✅ 5 tests pass (default plot_id today, accept dict, cancel rejected, logo picker, QSettings persistence) |

**Tests:** ~210 passed, ~30 skipped, 0 failed.
**Deliverable:** Manual flow — load plot → Generate (Mode A) → Eksport PDF → metadata dialog → file save → 9-page PDF opens.
**Known issue:** Polish chars in `plot_id` are sanitized to `_` in suggested filename (per regex `[^\w\-_. ]`). `\w` is Unicode so `ąęćźż` actually pass — but other diacritics outside `\w` get replaced. Acceptable.
**Deferred:** Phase 3.1 (multi-persona views), Phase 3.2 (macOS-only Polish font cross-platform handling).
```

Save the file.

- [ ] **Step 5: Commit STATE update**

```bash
git add docs/STATE.md
git commit -m "docs(STATE): mark Stage 1 Phase 3 (UI integration) complete

All 4 deliverables ready (adapter, dialog, window integration, tests). Manual
smoke passes end-to-end: load plot → Generate → Eksport → 9-page PDF."
```

- [ ] **Step 6: Final verification — clean working tree + branch status**

Run: `git status && git log --oneline -10`
Expected: working tree clean; last ~14 commits trace the Phase 3 implementation in order.

---

## Self-Review Checklist (already run)

**Spec coverage:**
- ✅ Sekcja 1 (file structure): Tasks 1, 2, 10, 15 cover all 5 new/modified files.
- ✅ Sekcja 2 (components): Task 2 covers `build_report_data` + all field mappings; Task 10 covers `ReportMetadataDialog`.
- ✅ Sekcja 3 (data flow): Task 17 implements `_on_export_pdf` end-to-end.
- ✅ Sekcja 4 (error handling): E1 (Task 17 guard), E2/E3 (Task 17 cancels), E4-E6 (Task 17 try/except), E7-E9 (already in Phase 2 / inherent to sync model).
- ✅ Sekcja 5 (testing): Tasks 2-9 cover all 10 report_builder tests; Tasks 10-14 cover all 5 dialog tests. Manual smoke is Task 19.

**Placeholder scan:** No "TBD", "TODO", "implement later". Every code step shows full code. The `_on_export_pdf` stub in Task 15 explicitly notes it will be replaced in Task 17.

**Type consistency:**
- `build_report_data` signature matches across Tasks 2, 3, 4 (kwargs-only `plot_id`, `plot_address`, `logo_path`).
- `ReportMetadataDialog.get_metadata` returns dict (Tasks 10, 11, 17).
- `_mode_a_results` shape `(plot, variants, indicators, verification)` consistent across Tasks 15, 16, 17, 18.
- `_invalidate_export_cache` introduced in Task 18, called by all invalidation paths.
