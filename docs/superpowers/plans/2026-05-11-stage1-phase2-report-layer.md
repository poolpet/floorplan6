# Stage 1 Phase 2 — Report Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wygenerowanie 9-stronicowego PDF feasibility report z CLI z fixture data — backend gotowy do Phase 3 (UI integration).

**Architecture:** 3-warstwowa separacja: `core/report_data.py` (POJO zbierający wyniki Mode A z `Plot`/`BuildableZone`/`PlotIndicators`/`VerificationResult[]`/`BuildupVariant[]`) → `core/report_renderer.py` (matplotlib figury) → `core/report_pdf.py` (reportlab assembly 9 stron z białej etykiety). Static content (słowniczek) jako module-level dict.

**Tech Stack:** Python 3.10+, reportlab 4.x (już zainstalowane), matplotlib 3.x (już), pypdf 4.x (nowa dep dla testów), pytest, dataclasses.

**Phase scope (Weeks 3-4 z roadmapy MVP):**
- Week 3: ReportData POJO + matplotlib figures + momepy evaluation
- Week 4: PDF assembly z reportlab + logo upload + hash + CLI

**NOT in scope:** UI dialog (Phase 3), multi-persona views (Phase 3 day 5), end-to-end ArchiCAD → PDF flow (Phase 3), OnGeo API.

---

## File Structure

### Files to create

| Path | Responsibility | LOC |
|---|---|---|
| `core/report_data.py` | `ReportData` dataclass + `estimate_units()` + glossary dict + hash | ~250 |
| `core/report_renderer.py` | matplotlib figures (5 types): plot+zone overlay, indicators bar, compliance table, variants 3-up, page header | ~350 |
| `core/report_pdf.py` | reportlab PDF assembly: 9 pages, logo, footer, CLI entry point | ~450 |
| `core/__main__.py` | nothing — but `python -m core.report_pdf` works because of module-level CLI |
| `tests/test_report_data.py` | 12 tests: dataclass fields, serialization, estimate_units, hash | ~180 |
| `tests/test_report_renderer.py` | 6 smoke tests: figures generate without exceptions, PNG output > 1KB | ~100 |
| `tests/test_report_pdf.py` | 6 tests: PDF generated, page count, disclaimer present, hash present, logo embedded | ~150 |
| `tests/fixtures/sample_report.py` | Reusable fixture: complete `ReportData` instance for tests | ~120 |
| `tests/fixtures/sample_logo.png` | 200×80 white-label test logo (generated programmatically in fixture) | binary |

### Files to modify

| Path | Change |
|---|---|
| `requirements.txt` | Add `pypdf>=4.0` (for test PDF inspection) |
| `docs/STATE.md` | After Phase 2 complete, append section marking it done |

### Files NOT touched

- `core/plot_subdivider.py` (Mode B) — out of scope
- `ui/*` — Phase 3 territory
- `bridge/*` — Phase 3 territory
- `rules/PL/constants.yaml` — pack already complete from Phase 1

---

## Setup

### Task 0: Verify clean baseline + feature branch

**Files:** none

- [ ] **Step 1: Verify all Phase 1 tests pass on main**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
git checkout main
git pull
pytest tests/ --ignore=tests/test_gui.py -q 2>&1 | tail -3
```

Expected: `~170 passed, 30 skipped, 1 xpassed`.

- [ ] **Step 2: Verify reportlab + matplotlib available**

```bash
python3 -c "import reportlab; import matplotlib; print('reportlab', reportlab.Version); print('matplotlib', matplotlib.__version__)"
```

Expected: prints both versions (reportlab 4.x, matplotlib 3.x).

- [ ] **Step 3: Create feature branch**

```bash
git checkout -b feature/stage1-phase2-report-layer
```

Expected: switched to new branch. Codex WIP files (M docs/*, ?? AGENTS.md, ?? AUDIT_REPORT.md, etc.) follow the branch as untracked working state. Do NOT commit them.

### Task 1: Add pypdf to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current requirements.txt**

```bash
cat requirements.txt
```

- [ ] **Step 2: Add pypdf line**

If `pypdf` not in file, append:

```
pypdf>=4.0  # PDF inspection for tests
```

- [ ] **Step 3: Install if not installed**

```bash
python3 -c "import pypdf" 2>&1 || pip install 'pypdf>=4.0'
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add pypdf>=4.0 for PDF test inspection"
```

---

## Week 3 — Report Data + Renderer

### Task 2: Create `ReportData` dataclass — TDD red

**Files:**
- Create: `tests/test_report_data.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_data.py`:

```python
"""Tests for core.report_data — ReportData dataclass and helpers."""
from __future__ import annotations

import pytest

from core.report_data import ReportData


class TestReportDataConstruction:
    def test_minimal_construction(self):
        """ReportData can be created with minimal required fields."""
        rd = ReportData(
            plot_id="dz. 1234/5",
            plot_address="ul. Przykładowa 12, Warszawa",
            plot_area_m2=1247.0,
        )
        assert rd.plot_id == "dz. 1234/5"
        assert rd.plot_area_m2 == 1247.0
        # Optional collections default to empty
        assert rd.verification_results == []
        assert rd.buildup_variants == []

    def test_all_fields_present(self):
        """All required ReportData attribute names exist."""
        rd = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0)
        for attr in [
            "plot_id", "plot_address", "plot_area_m2", "plot_perimeter_m",
            "mpzp_summary", "buildable_zone_m2", "buildable_zone_percent",
            "setbacks", "indicators", "verification_results", "buildup_variants",
            "logo_path", "generated_at", "tool_version", "pack_version",
            "data_hash",
        ]:
            assert hasattr(rd, attr), f"Missing attribute: {attr}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_report_data.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.report_data'`.

### Task 3: Implement `ReportData` dataclass — GREEN

**Files:**
- Create: `core/report_data.py`

- [ ] **Step 1: Write minimal `ReportData`**

Create `core/report_data.py`:

```python
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
```

- [ ] **Step 2: Run tests — both should pass**

```bash
pytest tests/test_report_data.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_report_data.py core/report_data.py
git commit -m "feat(report_data): add ReportData dataclass with all Mode A fields"
```

### Task 4: Add `estimate_units()` method + tests

**Files:**
- Modify: `core/report_data.py`
- Modify: `tests/test_report_data.py`

- [ ] **Step 1: Append tests**

Append to `tests/test_report_data.py`:

```python
class TestEstimateUnits:
    def test_basic_pum_divided_by_avg(self):
        """Estimate floor(PUM / avg_apartment_size)."""
        from core.report_data import estimate_units
        # PUM 562 m² ÷ 55 m² = 10.2 → 10 units
        assert estimate_units(pum_m2=562.0, avg_apartment_m2=55.0) == 10

    def test_default_avg_is_55m2(self):
        from core.report_data import estimate_units
        # PUM 100 / default 55 = 1.81 → 1
        assert estimate_units(pum_m2=100.0) == 1

    def test_zero_pum_returns_zero(self):
        from core.report_data import estimate_units
        assert estimate_units(pum_m2=0.0) == 0

    def test_below_one_apartment_returns_zero(self):
        from core.report_data import estimate_units
        # PUM 40 m² < 55 m² → 0 units
        assert estimate_units(pum_m2=40.0) == 0

    def test_custom_avg_size(self):
        from core.report_data import estimate_units
        # PUM 200 ÷ 80 = 2.5 → 2
        assert estimate_units(pum_m2=200.0, avg_apartment_m2=80.0) == 2

    def test_negative_pum_raises(self):
        from core.report_data import estimate_units
        with pytest.raises(ValueError, match="non-negative"):
            estimate_units(pum_m2=-10.0)
```

- [ ] **Step 2: Run — expect failures**

```bash
pytest tests/test_report_data.py::TestEstimateUnits -v
```

Expected: 6 failures (function doesn't exist).

- [ ] **Step 3: Add `estimate_units` to `core/report_data.py`**

Append after the dataclass definitions in `core/report_data.py`:

```python
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
```

- [ ] **Step 4: Re-run tests**

```bash
pytest tests/test_report_data.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_data.py tests/test_report_data.py
git commit -m "feat(report_data): add estimate_units() — PUM ÷ avg apartment size"
```

### Task 5: Add `compute_hash()` + glossary dict + serialization tests

**Files:**
- Modify: `core/report_data.py`
- Modify: `tests/test_report_data.py`

- [ ] **Step 1: Append tests for hash and glossary**

Append to `tests/test_report_data.py`:

```python
class TestComputeHash:
    def test_hash_deterministic(self):
        from core.report_data import ReportData, compute_hash
        rd = ReportData(plot_id="dz. 1234", plot_address="x", plot_area_m2=100.0)
        h1 = compute_hash(rd)
        h2 = compute_hash(rd)
        assert h1 == h2
        assert len(h1) == 16  # short hex prefix

    def test_hash_changes_with_plot_id(self):
        from core.report_data import ReportData, compute_hash
        rd1 = ReportData(plot_id="dz. 1234", plot_address="x", plot_area_m2=100.0)
        rd2 = ReportData(plot_id="dz. 5678", plot_address="x", plot_area_m2=100.0)
        assert compute_hash(rd1) != compute_hash(rd2)

    def test_hash_ignores_generated_at(self):
        """Same input data + different timestamp = same hash."""
        from datetime import datetime
        from core.report_data import ReportData, compute_hash
        rd1 = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0,
                          generated_at=datetime(2026, 1, 1))
        rd2 = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0,
                          generated_at=datetime(2026, 12, 31))
        assert compute_hash(rd1) == compute_hash(rd2)


class TestGlossary:
    def test_glossary_has_required_terms(self):
        from core.report_data import GLOSSARY
        required = {"WZ", "WIZ", "PBC", "MPZP", "linia zabudowy", "PUM"}
        assert required.issubset(GLOSSARY.keys()), \
            f"Missing terms: {required - set(GLOSSARY.keys())}"

    def test_glossary_entries_are_non_empty(self):
        from core.report_data import GLOSSARY
        for term, definition in GLOSSARY.items():
            assert definition.strip(), f"Empty definition for term: {term}"
```

- [ ] **Step 2: Run — expect 5 failures**

```bash
pytest tests/test_report_data.py -v
```

Expected: 8 pass, 5 fail (compute_hash + GLOSSARY missing).

- [ ] **Step 3: Add `compute_hash` and `GLOSSARY` to `core/report_data.py`**

Append to `core/report_data.py`:

```python
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
```

- [ ] **Step 4: Re-run tests**

```bash
pytest tests/test_report_data.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_data.py tests/test_report_data.py
git commit -m "feat(report_data): add compute_hash() + GLOSSARY for non-specialist readers"
```

---

### Task 6: Create `core/report_renderer.py` with `plot_zone_figure`

**Files:**
- Create: `core/report_renderer.py`
- Create: `tests/test_report_renderer.py`
- Create: `tests/fixtures/__init__.py` (empty)
- Create: `tests/fixtures/sample_report.py`

- [ ] **Step 1: Create sample fixture**

Create `tests/fixtures/__init__.py` (empty file):

```bash
touch tests/fixtures/__init__.py
```

Create `tests/fixtures/sample_report.py`:

```python
"""Reusable ReportData fixture for report_renderer + report_pdf tests."""
from __future__ import annotations

from datetime import datetime

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
```

- [ ] **Step 2: Write test for plot_zone_figure**

Create `tests/test_report_renderer.py`:

```python
"""Smoke tests for core.report_renderer matplotlib figures."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.sample_report import make_sample_report


class TestPlotZoneFigure:
    def test_returns_figure(self):
        from core.report_renderer import plot_zone_figure
        from matplotlib.figure import Figure
        rd = make_sample_report()
        fig = plot_zone_figure(rd)
        assert isinstance(fig, Figure)

    def test_savefig_produces_png(self, tmp_path):
        from core.report_renderer import plot_zone_figure
        rd = make_sample_report()
        fig = plot_zone_figure(rd)
        out = tmp_path / "plot_zone.png"
        fig.savefig(out, dpi=100)
        assert out.is_file()
        assert out.stat().st_size > 1024  # > 1 KB
```

- [ ] **Step 3: Run — expect failure**

```bash
pytest tests/test_report_renderer.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `core/report_renderer.py` with `plot_zone_figure`**

Create `core/report_renderer.py`:

```python
"""Report Renderer — matplotlib figures embedded into the PDF report.

Each figure is a Figure object. Caller (report_pdf.py) saves to PNG buffer,
embeds into reportlab Image flowable.

Convention:
    - All figures use figsize tuned for A4 portrait page width (8.27 in).
    - White background, dark text — PDF-print friendly.
    - No emoji icons in figures — pure ASCII / matplotlib markers (broader font compat).
"""
from __future__ import annotations

from typing import List

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from shapely import wkt

from core.report_data import ComplianceRow, IndicatorRow, ReportData, VariantInfo

# A4 portrait usable width minus margins (in inches).
A4_WIDTH_IN = 7.0


def plot_zone_figure(rd: ReportData) -> Figure:
    """Plot polygon + buildable zone overlay + setback annotations.

    Page 4 of the report. Shows the plot outline (black), buildable zone
    (green fill), and labels for setback distances.
    """
    fig, ax = plt.subplots(figsize=(A4_WIDTH_IN, 5.0))

    if rd.plot_polygon_wkt:
        plot_poly = wkt.loads(rd.plot_polygon_wkt)
        x, y = plot_poly.exterior.xy
        ax.plot(x, y, color="black", linewidth=1.5, label="Granica działki")
        ax.fill(x, y, color="#FFFAF0", alpha=0.3)

    if rd.buildable_polygon_wkt:
        bz_poly = wkt.loads(rd.buildable_polygon_wkt)
        bx, by = bz_poly.exterior.xy
        ax.fill(bx, by, color="#C8E6C9", alpha=0.6, label="Buildable zone")
        ax.plot(bx, by, color="#2E7D32", linewidth=1.0, linestyle="--")

    # Setback annotations
    sb = rd.setbacks
    ax.text(
        0.02, 0.98,
        f"Linia zabudowy:\n  od drogi: {sb.front_m} m\n"
        f"  od boku: {sb.side_m} m\n  od tyłu: {sb.rear_m} m",
        transform=ax.transAxes,
        va="top", fontsize=9,
        bbox=dict(facecolor="white", edgecolor="gray", boxstyle="round,pad=0.5"),
    )

    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"Działka {rd.plot_id} — strefa zabudowy", fontsize=11)
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    return fig
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_report_renderer.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add core/report_renderer.py tests/test_report_renderer.py tests/fixtures/__init__.py tests/fixtures/sample_report.py
git commit -m "feat(report_renderer): add plot_zone_figure (page 4 viz)"
```

### Task 7: Add `indicators_bar_chart` figure

**Files:**
- Modify: `core/report_renderer.py`
- Modify: `tests/test_report_renderer.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_renderer.py`:

```python
class TestIndicatorsBarChart:
    def test_returns_figure(self):
        from core.report_renderer import indicators_bar_chart
        from matplotlib.figure import Figure
        rd = make_sample_report()
        fig = indicators_bar_chart(rd)
        assert isinstance(fig, Figure)

    def test_renders_with_empty_indicators(self):
        """Should not crash if indicators list is empty."""
        from core.report_data import ReportData
        from core.report_renderer import indicators_bar_chart
        rd = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0)
        fig = indicators_bar_chart(rd)
        assert fig is not None  # graceful handling
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_renderer.py::TestIndicatorsBarChart -v
```

Expected: 2 failures.

- [ ] **Step 3: Add `indicators_bar_chart` to `core/report_renderer.py`**

Append to `core/report_renderer.py`:

```python
# Status color mapping (zielony/żółty/czerwony, plus text-friendly symbols).
STATUS_COLOR = {
    "OK": "#27AE60",
    "WARN": "#F39C12",
    "VIOLATION": "#E74C3C",
    "ZGODNY": "#27AE60",
    "OSTRZEZENIE": "#F39C12",
    "NIEZGODNY": "#E74C3C",
    "NIEWERYFIKOWANY": "#95A5A6",
}

STATUS_SYMBOL = {
    "OK": "+",
    "WARN": "!",
    "VIOLATION": "X",
    "ZGODNY": "+",
    "OSTRZEZENIE": "!",
    "NIEZGODNY": "X",
    "NIEWERYFIKOWANY": "?",
}


def indicators_bar_chart(rd: ReportData) -> Figure:
    """Horizontal bar chart: designed vs limit for WZ, WIZ, PBC.

    Page 5 of the report. Each row shows a colored bar (length = designed
    fraction of limit, capped at 1.0) plus the status icon and a numeric label.
    """
    fig, ax = plt.subplots(figsize=(A4_WIDTH_IN, 3.5))
    rows = rd.indicators or []

    if not rows:
        ax.text(0.5, 0.5, "Brak wskaźników", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray")
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    y_positions = list(range(len(rows)))
    fractions = [
        (row.designed / row.limit if row.limit > 0 else 0.0)
        for row in rows
    ]
    colors = [STATUS_COLOR.get(row.status, "#888") for row in rows]

    ax.barh(y_positions, fractions, color=colors, alpha=0.75, edgecolor="black")
    ax.axvline(x=1.0, color="red", linestyle="--", linewidth=1, label="Limit")
    ax.axvline(x=1.05, color="orange", linestyle=":", linewidth=1, label="Limit + 5% (Q14)")

    # Labels
    ax.set_yticks(y_positions)
    ax.set_yticklabels([row.name for row in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.20)
    ax.set_xlabel("Designed ÷ Limit")

    for i, row in enumerate(rows):
        symbol = STATUS_SYMBOL.get(row.status, "?")
        label = f"{row.designed:.2f}{row.unit} / {row.limit:.2f}{row.unit}  [{symbol}]"
        ax.text(1.21, i, label, va="center", fontsize=9)

    ax.set_title("Wskaźniki MPZP — designed vs limit", fontsize=11)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    fig.tight_layout()
    return fig
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_renderer.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_renderer.py tests/test_report_renderer.py
git commit -m "feat(report_renderer): add indicators_bar_chart (page 5 viz)"
```

### Task 8: Add `variants_grid_figure`

**Files:**
- Modify: `core/report_renderer.py`
- Modify: `tests/test_report_renderer.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_renderer.py`:

```python
class TestVariantsGrid:
    def test_returns_figure(self):
        from core.report_renderer import variants_grid_figure
        from matplotlib.figure import Figure
        rd = make_sample_report()
        fig = variants_grid_figure(rd)
        assert isinstance(fig, Figure)

    def test_handles_fewer_than_3_variants(self):
        from core.report_data import ReportData, VariantInfo
        from core.report_renderer import variants_grid_figure
        rd = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0,
                          buildup_variants=[
                              VariantInfo(number=1, footprint_area_m2=50.0,
                                          wz=0.5, wiz=0.5, pbc_percent=30.0,
                                          estimated_units=1),
                          ])
        fig = variants_grid_figure(rd)
        assert fig is not None
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_renderer.py::TestVariantsGrid -v
```

Expected: 2 failures.

- [ ] **Step 3: Add `variants_grid_figure` to `core/report_renderer.py`**

Append to `core/report_renderer.py`:

```python
def variants_grid_figure(rd: ReportData) -> Figure:
    """3-up grid showing each buildup variant with WZ + units estimate.

    Page 7 of the report. Each panel = one variant. Shows polygon shape,
    footprint area, WZ, and estimated apartment count.
    """
    variants = rd.buildup_variants or []
    n = max(1, len(variants))
    fig, axes = plt.subplots(1, n, figsize=(A4_WIDTH_IN, 3.5), squeeze=False)
    axes = axes.flatten()

    for i, variant in enumerate(variants):
        ax = axes[i]
        # Simple placeholder: draw a rectangle proportional to footprint area.
        # If we have an actual polygon WKT per variant in future, render that.
        side = (variant.footprint_area_m2) ** 0.5
        ax.add_patch(mpatches.Rectangle((0, 0), side, side,
                                          facecolor="#90CAF9", edgecolor="black"))
        ax.set_xlim(-5, side + 5)
        ax.set_ylim(-5, side + 5)
        ax.set_aspect("equal")
        ax.set_title(f"Wariant {chr(ord('A') + variant.number - 1)}", fontsize=10)
        ax.text(0.5, -0.15,
                f"{variant.footprint_area_m2:.0f} m²\n"
                f"WZ {variant.wz:.2f}\n"
                f"~{variant.estimated_units} mieszkań",
                transform=ax.transAxes, ha="center", va="top", fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused panels
    for j in range(len(variants), n):
        axes[j].set_axis_off()

    fig.suptitle("Warianty zabudowy + szacunek liczby mieszkań", fontsize=11)
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    return fig
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_renderer.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_renderer.py tests/test_report_renderer.py
git commit -m "feat(report_renderer): add variants_grid_figure (page 7 viz)"
```

### Task 9: momepy evaluation — decision point

**Files:** none (research only)

- [ ] **Step 1: Try installing momepy**

```bash
python3 -c "import momepy; print(momepy.__version__)" 2>&1 || pip install momepy
```

- [ ] **Step 2: Try replacing one metric — quick spike**

Create a throwaway file `notebooks/momepy_eval.py`:

```python
"""Quick eval: does momepy.shape simplify Plot geometry metrics?"""
import geopandas as gpd
from shapely.geometry import Polygon
import momepy

rect = Polygon([(0, 0), (30, 0), (30, 40), (0, 40)])
gdf = gpd.GeoDataFrame(geometry=[rect])

# circular_compactness: how close to a circle (0..1, 1 = circle)
cc = momepy.circular_compactness(gdf).iloc[0]
print(f"circular_compactness: {cc:.3f}")

# Form factor
ff = momepy.form_factor(gdf, "geometry").iloc[0] if False else None  # API may differ
print(f"form_factor: {ff}")

# Convexity
conv = momepy.convexity(gdf).iloc[0]
print(f"convexity: {conv:.3f}")
```

```bash
python3 notebooks/momepy_eval.py 2>&1 | head -20
```

- [ ] **Step 3: Decision**

If the API was simple and the metrics map cleanly to fields we'd otherwise hand-compute → **GO**: add `momepy` to `requirements.txt` and use it in `core/plot_indicators.py` for shape factor (helps scoring future Mode B variants). Otherwise → **NO-GO**: stop, document decision.

Document the decision in the commit message either way. The plan estimated this would save ≥30% of indicator code — that's the threshold.

- [ ] **Step 4: Commit the decision (with or without code change)**

If **GO**: implement and commit:
```bash
git add requirements.txt core/plot_indicators.py notebooks/momepy_eval.py
git commit -m "feat(indicators): integrate momepy for shape factor — saves N% code"
```

If **NO-GO**: just commit the eval script + decision note in `notebooks/momepy_eval.py`:
```bash
git add notebooks/momepy_eval.py
git commit -m "docs(momepy): eval declined — overhead not justified for current metrics"
```

**Self-review:** does adding momepy actually simplify code, or does it just add a dependency? When in doubt, NO-GO. We can revisit in Phase 3+.

---

## Week 4 — PDF Assembly

### Task 10: PDF skeleton — cover page + reportlab boilerplate

**Files:**
- Create: `core/report_pdf.py`
- Create: `tests/test_report_pdf.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_report_pdf.py`:

```python
"""Tests for core.report_pdf — PDF assembly via reportlab."""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.fixtures.sample_report import make_sample_report


class TestPDFGeneration:
    def test_pdf_is_created(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        assert out.is_file()
        assert out.stat().st_size > 5000  # > 5 KB

    def test_pdf_has_cover_page(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 1
        text = reader.pages[0].extract_text()
        assert rd.plot_id in text
        assert rd.plot_address in text
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `core/report_pdf.py` with cover page**

Create `core/report_pdf.py`:

```python
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
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)
from reportlab.lib import colors

from core.report_data import ReportData, compute_hash


# --- Style setup (module-level — reused across pages) ---

_styles = getSampleStyleSheet()
TITLE_STYLE = ParagraphStyle(
    name="Title", parent=_styles["Title"], fontSize=20, spaceAfter=12, alignment=1,  # center
)
H1_STYLE = ParagraphStyle(
    name="H1", parent=_styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=8,
)
BODY_STYLE = ParagraphStyle(
    name="Body", parent=_styles["BodyText"], fontSize=10, leading=13, spaceAfter=6,
)
SMALL_STYLE = ParagraphStyle(
    name="Small", parent=_styles["BodyText"], fontSize=8, leading=10, textColor=colors.grey,
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


def generate_pdf(rd: ReportData, output_path: Path) -> Path:
    """Generate the full 9-page feasibility report PDF.

    Args:
        rd: Populated ReportData (compute_hash will be called).
        output_path: Where to write the PDF file.

    Returns:
        output_path (for convenience).
    """
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

    doc.build(flowables)
    return output_path
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 2 passed (PDF generated + cover has plot info).

- [ ] **Step 5: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add PDF skeleton with cover page (page 1)"
```

### Task 11: Add executive summary + data inputs pages (2-3)

**Files:**
- Modify: `core/report_pdf.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_pdf.py`:

```python
    def test_pdf_has_exec_summary_and_inputs(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 3
        # Exec summary should mention WZ designed
        text2 = reader.pages[1].extract_text()
        assert "Executive summary" in text2 or "Podsumowanie" in text2
        # Data inputs should mention MPZP
        text3 = reader.pages[2].extract_text()
        assert "MPZP" in text3
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_pdf.py::TestPDFGeneration::test_pdf_has_exec_summary_and_inputs -v
```

- [ ] **Step 3: Add page builders to `core/report_pdf.py`**

Insert before `generate_pdf` in `core/report_pdf.py`:

```python
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
```

Update `generate_pdf` to use them:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add executive summary + data inputs pages (pages 2-3)"
```

### Task 12: Add buildable zone + indicators pages (4-5) with embedded figures

**Files:**
- Modify: `core/report_pdf.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_pdf.py`:

```python
    def test_pdf_has_buildable_and_indicators_pages(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 5
```

- [ ] **Step 2: Run — expect failure (only 3 pages)**

```bash
pytest tests/test_report_pdf.py::TestPDFGeneration::test_pdf_has_buildable_and_indicators_pages -v
```

- [ ] **Step 3: Add figure-embedding helper + page builders**

Insert before `cover_page` in `core/report_pdf.py`:

```python
from matplotlib.figure import Figure


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
```

Insert before `generate_pdf`:

```python
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
```

Update `generate_pdf` to extend with new pages:

```python
    flowables.extend(cover_page(rd))
    flowables.extend(exec_summary_page(rd))
    flowables.extend(data_inputs_page(rd))
    flowables.extend(buildable_zone_page(rd))
    flowables.extend(indicators_page(rd))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add buildable zone + indicators pages with embedded figures (pages 4-5)"
```

### Task 13: Add compliance + variants pages (6-7)

**Files:**
- Modify: `core/report_pdf.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_pdf.py`:

```python
    def test_pdf_has_compliance_and_variants_pages(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 7
        compliance_text = reader.pages[5].extract_text()
        assert "wt_001" in compliance_text or "Odległość" in compliance_text
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_pdf.py::TestPDFGeneration::test_pdf_has_compliance_and_variants_pages -v
```

- [ ] **Step 3: Add page builders**

Insert before `generate_pdf` in `core/report_pdf.py`:

```python
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
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
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
```

Extend `generate_pdf`:

```python
    flowables.extend(compliance_page(rd))
    flowables.extend(variants_page(rd))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add compliance + variants pages (pages 6-7)"
```

### Task 14: Add glossary + metadata pages (8-9)

**Files:**
- Modify: `core/report_pdf.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_pdf.py`:

```python
    def test_pdf_has_glossary_and_metadata(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 9
        glossary_text = reader.pages[7].extract_text()
        assert "MPZP" in glossary_text
        assert "WZ" in glossary_text
        metadata_text = reader.pages[8].extract_text()
        assert rd.data_hash in metadata_text
        assert "disclaimer" in metadata_text.lower() or "informacyjny" in metadata_text.lower()
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_pdf.py::TestPDFGeneration::test_pdf_has_glossary_and_metadata -v
```

- [ ] **Step 3: Add page builders**

Insert before `generate_pdf` in `core/report_pdf.py`:

```python
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
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0E0E0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
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
```

Extend `generate_pdf`:

```python
    flowables.extend(glossary_page(rd))
    flowables.extend(metadata_page(rd))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add glossary + metadata + disclaimer pages (pages 8-9)"
```

### Task 15: Add CLI entry point + smoke test

**Files:**
- Modify: `core/report_pdf.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Append test**

Append to `tests/test_report_pdf.py`:

```python
class TestCLI:
    def test_cli_generates_sample(self, tmp_path, monkeypatch):
        """Running `python -m core.report_pdf --fixture sample --out X` works."""
        import subprocess
        out = tmp_path / "cli_sample.pdf"
        result = subprocess.run(
            ["python3", "-m", "core.report_pdf", "--fixture", "sample", "--out", str(out)],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.is_file()
        assert out.stat().st_size > 20000  # at least 20 KB for 9 pages
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_report_pdf.py::TestCLI -v
```

- [ ] **Step 3: Add CLI to `core/report_pdf.py`**

Append to bottom of `core/report_pdf.py`:

```python
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
```

- [ ] **Step 4: Manual smoke test**

```bash
python3 -m core.report_pdf --fixture sample --out /tmp/floorplan6_sample.pdf
```

Expected output: `Generated: /tmp/floorplan6_sample.pdf (NNNNN bytes)`.

Open the PDF visually if possible:
```bash
open /tmp/floorplan6_sample.pdf  # macOS
```

Verify: 9 pages, no broken images, no missing text, hash visible on last page.

- [ ] **Step 5: Run automated CLI test**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add core/report_pdf.py tests/test_report_pdf.py
git commit -m "feat(report_pdf): add CLI entry point — python -m core.report_pdf"
```

### Task 16: Add logo upload support — programmatic test logo

**Files:**
- Modify: `tests/fixtures/sample_report.py`
- Modify: `tests/test_report_pdf.py`

- [ ] **Step 1: Add helper to generate a test PNG logo programmatically**

Append to `tests/fixtures/sample_report.py`:

```python
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
```

- [ ] **Step 2: Append test for white-label logo**

Append to `tests/test_report_pdf.py`:

```python
    def test_pdf_with_logo(self, tmp_path):
        from core.report_pdf import generate_pdf
        from tests.fixtures.sample_report import make_sample_logo
        logo_path = make_sample_logo(tmp_path / "logo.png")
        rd = make_sample_report()
        rd.logo_path = logo_path
        out = tmp_path / "report_with_logo.pdf"
        generate_pdf(rd, out)
        assert out.is_file()
        # PDF with logo should be larger than without (image bytes embedded)
        assert out.stat().st_size > 25000
```

- [ ] **Step 3: Run tests (cover_page already handles logo_path — see Task 10)**

```bash
pytest tests/test_report_pdf.py::TestPDFGeneration::test_pdf_with_logo -v
```

Expected: 1 passed (cover_page already conditionally embeds the logo).

- [ ] **Step 4: Run full report_pdf suite**

```bash
pytest tests/test_report_pdf.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sample_report.py tests/test_report_pdf.py
git commit -m "test(report_pdf): verify white-label logo embedding works"
```

### Task 17: Update `docs/STATE.md` with Phase 2 completion

**Files:**
- Modify: `docs/STATE.md`

- [ ] **Step 1: Append Phase 2 section to STATE.md**

Edit `docs/STATE.md`. Find the "Stage 1 — Phase 1 (Pack Architecture)" section we added at the end of Phase 1. **Below** it, **above** "What's next", add:

```markdown
### Stage 1 — Phase 2 (Report Layer) — COMPLETED 2026-MM-DD

| Component | Status |
|---|---|
| `core/report_data.py` | ✅ `ReportData` dataclass + `estimate_units()` + `compute_hash()` + `GLOSSARY` |
| `core/report_renderer.py` | ✅ 3 matplotlib figures: plot_zone, indicators_bar, variants_grid |
| `core/report_pdf.py` | ✅ 9-page reportlab assembly + CLI (`python -m core.report_pdf`) |
| `tests/fixtures/sample_report.py` | ✅ Reusable test fixture + sample logo generator |
| `tests/test_report_data.py` | ✅ 13 tests pass (dataclass, estimate_units, hash, glossary) |
| `tests/test_report_renderer.py` | ✅ 6 smoke tests pass |
| `tests/test_report_pdf.py` | ✅ 8 tests pass (cover, sections, logo, CLI) |
| `requirements.txt` | ✅ Added pypdf>=4.0 for PDF inspection |
| momepy evaluation | ✅ Decision documented (see commit for go/no-go) |

**Tests:** ~195 passed (170 from Phase 1 baseline + ~27 new).
**Deliverable:** `python -m core.report_pdf --fixture sample --out report.pdf` produces 9-page PDF.
**Next:** Phase 3 — UI integration + multi-persona + macOS CI.
```

Replace MM-DD with actual date.

- [ ] **Step 2: Commit**

```bash
git add docs/STATE.md
git commit -m "docs(STATE): mark Stage 1 Phase 2 (report layer) complete"
```

### Task 18: Final Phase 2 verification

**Files:** none

- [ ] **Step 1: Full test suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q 2>&1 | tail -3
```

Expected: ~195 passed.

- [ ] **Step 2: End-to-end CLI demo**

```bash
python3 -m core.report_pdf --fixture sample --out /tmp/floorplan6_phase2_final.pdf
ls -la /tmp/floorplan6_phase2_final.pdf
```

Expected: PDF generated, size > 20 KB.

- [ ] **Step 3: Open PDF visually for manual review**

```bash
open /tmp/floorplan6_phase2_final.pdf  # macOS
```

Manual checklist — open the PDF and confirm:
- [ ] Page 1 (Cover): tytuł "Raport analizy działki", adres, summary table
- [ ] Page 2 (Exec summary): top-line numbers (max footprint, PUM, bio area)
- [ ] Page 3 (Dane wejściowe): MPZP table
- [ ] Page 4 (Buildable zone): matplotlib figure
- [ ] Page 5 (Indicators): bar chart with WZ/WIZ/PBC
- [ ] Page 6 (Compliance): table with 3 sample rules
- [ ] Page 7 (Variants): 3-up panels with estimated units
- [ ] Page 8 (Glossary): table of terms
- [ ] Page 9 (Metadata + Disclaimer): hash + disclaimer text

If any page is broken/missing, fix and re-commit. Otherwise:

- [ ] **Step 4: Confirm no `from config import` regressions**

```bash
grep -rn "from config import\|^import config" \
  --include="*.py" \
  --exclude-dir=__pycache__ \
  --exclude-dir=notebooks \
  --exclude-dir=.git \
  .
```

Expected: empty (Phase 1's cleanup holds).

- [ ] **Step 5: Branch ready summary**

```bash
git log --oneline feature/stage1-phase2-report-layer --not main | head -20
```

Should show ~16-18 commits, all conventional commits.

---

## Phase 2 Complete

After all 18 tasks:
- ✅ `core/report_data.py` + `report_renderer.py` + `report_pdf.py` in place
- ✅ ~195 tests passing (170 baseline + 27 new)
- ✅ `python -m core.report_pdf --fixture sample --out X.pdf` generates 9-page PDF
- ✅ White-label logo support
- ✅ Hash for data provenance
- ✅ Disclaimer prawny

**Ready for Phase 3:** UI integration (`ui/stage1_report_dialog.py`), multi-persona views (architekt / developer), macOS CI, beta testing.

---

## Open questions deferred to Phase 3

1. **Polygon WKT in BuildupVariant** — current `variants_grid_figure` draws a placeholder square. If `BuildupVariant` gains a polygon field upstream (e.g. in site_planner), update the figure to render the real shape.

2. **Cover page logo dimensions** — current spec is 200×80 px (4 cm × 1.6 cm in PDF). Real biuro logos may have different aspect ratios. Consider auto-scaling to max box.

3. **Multi-persona text variations** — Phase 3 day 5 work. Same data, different exec summary phrasing for architect vs developer.

4. **`tests/fixtures/` discovery on CI** — verify `tests/fixtures/__init__.py` works on Linux CI runner. Path manipulation may differ.
