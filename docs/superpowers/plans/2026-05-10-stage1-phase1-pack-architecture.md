# Stage 1 Phase 1 — Pack Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wprowadzić modularną architekturę code-pack dla reguł MPZP/WT z proof-of-concept polskim packiem (`rules/PL/`), bez zmiany behawioru systemu (180 testów zielonych przed i po refaktorze).

**Architecture:** Wszystkie reguły i rule-driven constants przeniesione do `rules/PL/` (manifest pack.yaml + wt_rules.json + constants.yaml + user_rules.json). Generic loader `rules/_loader.py` ładuje pack z walidacją schema (pydantic). Kod produkcyjny dostaje `CodePack` na starcie i konsumuje reguły przez `pack.rules` / `pack.constants`. `config.py` zawiera tylko Python-runtime stałe.

**Tech Stack:** Python 3.10+, pydantic 2.x (nowa zależność), PyYAML (już w deps przez archicad), pytest, JSON Schema dla wt_rules, YAML dla pack.yaml + constants.

**Phase scope (Weeks 1-2 z roadmapy MVP):**
- Week 1: Pack foundation — folder struktura, manifest, loader + schema, integracja z `plot_verifier.py`
- Week 2: Constants migration — extract z `config.py`, refactor importów w 5 modułach core

**NOT in scope:** Report Layer (Phase 2), UI (Phase 3), Mode B subdivision changes, UK/DE/US pack content.

---

## File Structure

### Files to create

| Path | Responsibility | LOC |
|---|---|---|
| `rules/PL/pack.yaml` | Manifest packa PL: id, version, locale, references, files | ~30 |
| `rules/PL/constants.yaml` | Rule-driven stałe wyciągnięte z `config.py` | ~120 |
| `rules/_loader.py` | `CodePack` dataclass + `load_pack()` function | ~80 |
| `rules/_schema.py` | Pydantic models dla pack manifest + constants validation | ~80 |
| `rules/README.md` | Dokumentacja "How to add a country pack" | ~80 |
| `tests/test_pack_loader.py` | Testy `load_pack()`: success, missing, schema errors | ~150 |
| `tests/test_pack_constants.py` | Testy `constants.yaml`: schema valid, all keys present, types correct | ~70 |

### Files to move

| From | To |
|---|---|
| `rules/wt_rules.json` | `rules/PL/wt_rules.json` |
| `rules/user_rules.json` | `rules/PL/user_rules.json` |

### Files to modify

| Path | Change |
|---|---|
| `core/plot_verifier.py:37,131,133` | `RULES_DIR` → load via `rules._loader.load_pack("PL")` |
| `core/cpsat_solver.py` | Replace `from config import WT_MIN_AREA, WT_MAX_AREA, HUB_*` with `pack.constants[...]` |
| `core/validator.py` | Replace `from config import WT_MAX_AREA, PROPORTION_*` with pack-driven |
| `core/scorer.py` | Replace `from config import DEFAULT_SCORER_WEIGHTS, ORIENTATION_QUALITY` |
| `core/site_planner.py` | Replace `from config import` (parking ratio, building class) |
| `core/floor_compute.py` | Replace `from config import APARTMENT_*, WT_BUILDING_CLASS_THRESHOLDS` |
| `core/floor_validation.py` | Replace `from config import WT_CORRIDOR_*, WT_DOJSCIE_*` |
| `core/floor_layout.py` | Replace `from config import APARTMENT_MIX_DEFAULT, FLOOR_RESERVE_RATIO` |
| `config.py` | Remove all rule-driven constants; keep only Python-runtime (e.g. SCALE) |
| `requirements.txt` | Add `pydantic>=2.0` |

### Files NOT touched

- `core/plot_subdivider.py` (Mode B, 2669 linii — defer post-MVP)
- `core/cpsat_solver.py` solver constraints logic — only imports change
- `bridge/*` — rules are pre-loaded by UI before bridge invocation
- `viz/*` — no dependency on rules

---

## Setup

### Task 0: Verify clean baseline

**Files:** none

- [ ] **Step 1: Verify all tests pass on main**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: `144 passed, 30 skipped, 1 xpassed` (or close to that — check `docs/STATE.md` for latest)

- [ ] **Step 2: Verify pydantic available or install**

```bash
python -c "import pydantic; print(pydantic.VERSION)"
```

Expected: prints version `2.x.y`. If ImportError, run `pip install 'pydantic>=2.0'` and add to `requirements.txt`.

- [ ] **Step 3: Create feature branch**

```bash
git checkout -b feature/stage1-phase1-pack-architecture
```

Expected: switched to new branch.

---

## Week 1 — Pack Foundation

### Task 1: Move existing rules to `rules/PL/`

**Files:**
- Move: `rules/wt_rules.json` → `rules/PL/wt_rules.json`
- Move: `rules/user_rules.json` → `rules/PL/user_rules.json`
- Modify: `core/plot_verifier.py:37`

- [ ] **Step 1: Create `rules/PL/` directory and move files**

```bash
mkdir -p rules/PL
git mv rules/wt_rules.json rules/PL/wt_rules.json
git mv rules/user_rules.json rules/PL/user_rules.json
```

Expected: `git status` shows two renames.

- [ ] **Step 2: Update `RULES_DIR` in `plot_verifier.py`**

Edit `core/plot_verifier.py` line 37:

```python
# OLD:
RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

# NEW:
RULES_DIR = Path(__file__).resolve().parent.parent / "rules" / "PL"
```

- [ ] **Step 3: Run plot_verifier tests**

```bash
pytest tests/test_plot_verifier.py -v
```

Expected: 14 passed.

- [ ] **Step 4: Run full non-GUI suite to verify no regression**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: same count as Step 1 of Task 0 (144 passed).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(rules): move wt_rules.json + user_rules.json to rules/PL/"
```

---

### Task 2: Add `pydantic` to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current requirements.txt**

```bash
cat requirements.txt
```

- [ ] **Step 2: Add pydantic line if missing**

If `pydantic` not in file, append:

```
pydantic>=2.0
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add pydantic>=2.0 for code pack schema validation"
```

---

### Task 3: Write Pydantic schema models (`rules/_schema.py`)

**Files:**
- Create: `rules/_schema.py`
- Test: `tests/test_pack_loader.py` (created in Task 5, not yet)

- [ ] **Step 1: Create `rules/_schema.py` with manifest + constants schemas**

```python
"""Pydantic schemas for code pack validation.

Schema 1: PackManifest — validates rules/{PACK}/pack.yaml
Schema 2: PackConstants — validates rules/{PACK}/constants.yaml

These are the contract every code pack must satisfy. Validation happens
at load time in `rules._loader.load_pack()`.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PackReference(BaseModel):
    """A legal/regulatory reference cited by the pack."""
    id: str
    title: str
    url: Optional[str] = None


class PackFiles(BaseModel):
    """Filenames inside the pack directory."""
    rules: str = "wt_rules.json"
    constants: str = "constants.yaml"
    user_overrides: str = "user_rules.json"


class PackManifest(BaseModel):
    """Schema for pack.yaml.

    Every code pack must declare its identity, locale, version compatibility,
    and the files it provides.
    """
    code_pack_id: str = Field(..., description="ISO country code or custom id, e.g. 'PL'")
    country_code: str
    locale: str = Field(..., description="POSIX locale like 'pl_PL'")
    version: str = Field(..., description="Pack version, e.g. '1.0'")
    version_compat: str = Field(..., description="FloorPlan6 version range, e.g. '>=0.4.0'")
    display_name: str
    display_name_en: Optional[str] = None
    description: str
    references: List[PackReference] = Field(default_factory=list)
    files: PackFiles = Field(default_factory=PackFiles)


class WTAreaConstants(BaseModel):
    """WT min/max area constants (m²)."""
    bathroom_m2: float
    wc_m2: float


class SetbackDefaults(BaseModel):
    """Default setbacks (m) used when MPZP doesn't specify."""
    front_m: float
    side_m: float
    rear_m: float
    well_to_boundary_m: float


class BuildingClassThresholds(BaseModel):
    """Building height class thresholds (m) per WT."""
    N_max_height_m: float
    SW_max_height_m: float
    W_max_height_m: float
    WW_above_m: float


class PackConstants(BaseModel):
    """Schema for constants.yaml.

    All rule-driven constants extracted from config.py. Adding a new constant
    requires updating this schema (single source of truth).
    """
    # WT area limits
    wt_min_area: Dict[str, float]
    wt_max_area: Dict[str, float]
    wt_min_width: Dict[str, float]

    # Setbacks
    setback_defaults: SetbackDefaults

    # Hub
    hub_min_percent: Dict[str, float]
    hub_max_percent: float
    hub_min_area: Dict[str, float]

    # Apartment types + areas
    apartment_min_area: Dict[str, float]
    apartment_opt_area: Dict[str, float]
    apartment_max_aspect: float
    apartment_mix_default: Dict[str, float]

    # Building class
    building_class: BuildingClassThresholds

    # Corridors + escape
    wt_corridor_internal_min: float
    wt_corridor_public_min: float
    wt_dojscie_max_1klatka: float
    wt_dojscie_max_2klatki: float
    door_min_width: float

    # Stairs
    wt_stair_bieg_width: float
    wt_stair_spocznik_width: float
    wt_stair_step_height_max: float
    wt_stair_blondel: float
    wt_stair_step_width_min: float

    # Elevator
    wt_elevator_height_threshold: float
    wt_elevator_shaft_w: float
    wt_elevator_shaft_l: float
    wt_elevator_fire_w: float
    wt_elevator_fire_l: float

    # Wall thicknesses
    wall_thickness_structural: float
    wall_thickness_partition: float
    wall_thickness_bathroom: float

    # Proportions
    proportion_optimal: float
    proportion_max: float
    proportion_absolute_max: float

    # Orientation
    orientation_quality: Dict[str, float]

    # Scorer
    default_scorer_weights: Dict[str, float]

    # Floor reserve
    floor_reserve_ratio: float

    # Parking
    parking_ratio_per_unit: float

    # Mode B (Stage 1 subdivision)
    min_subplot_front_m: float

    # Przedsionek depth per building class
    wt_przedsionek_depth: Dict[str, float]
```

- [ ] **Step 2: Verify file parses**

```bash
python -c "from rules._schema import PackManifest, PackConstants; print('OK')"
```

Expected: `OK`. Also creates `rules/__init__.py` if needed (Python module discovery).

- [ ] **Step 3: Create `rules/__init__.py` if missing**

```bash
test -f rules/__init__.py || touch rules/__init__.py
```

- [ ] **Step 4: Re-verify import**

```bash
python -c "from rules._schema import PackManifest, PackConstants; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add rules/__init__.py rules/_schema.py
git commit -m "feat(rules): add Pydantic schemas for pack manifest and constants"
```

---

### Task 4: Write `rules/PL/pack.yaml` manifest

**Files:**
- Create: `rules/PL/pack.yaml`

- [ ] **Step 1: Create the manifest**

Write `rules/PL/pack.yaml`:

```yaml
code_pack_id: PL
country_code: PL
locale: pl_PL
version: "1.0"
version_compat: ">=0.4.0"
display_name: "Polska — Warunki Techniczne 2002"
display_name_en: "Poland — WT 2002"
description: "Polski pack: 19 reguł WT 2002, MPZP defaults, constants z config.py"
references:
  - id: WT_2002
    title: "Rozporządzenie Ministra Infrastruktury z 12 kwietnia 2002 (Dz.U. 2022 poz. 1225)"
    url: "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20020750690"
  - id: KP_KOMUNIKACJA
    title: "WT § 237 — minimalne szerokości komunikacji"
files:
  rules: wt_rules.json
  constants: constants.yaml
  user_overrides: user_rules.json
```

- [ ] **Step 2: Verify YAML parses + matches schema**

```bash
python -c "
import yaml
from rules._schema import PackManifest
data = yaml.safe_load(open('rules/PL/pack.yaml'))
m = PackManifest(**data)
print(f'OK: {m.code_pack_id} v{m.version}')
"
```

Expected: `OK: PL v1.0`.

- [ ] **Step 3: Commit**

```bash
git add rules/PL/pack.yaml
git commit -m "feat(rules): add PL pack manifest"
```

---

### Task 5: Write `rules/_loader.py` — TDD red

**Files:**
- Create: `tests/test_pack_loader.py` (initial structure with failing tests)

- [ ] **Step 1: Write the failing test for `load_pack` happy path**

Create `tests/test_pack_loader.py`:

```python
"""Tests for rules._loader.load_pack()."""
from __future__ import annotations

import pytest

from rules._loader import CodePack, CodePackError, load_pack


class TestLoadPackHappyPath:
    def test_load_pl_pack_returns_codepack(self):
        pack = load_pack("PL")
        assert isinstance(pack, CodePack)
        assert pack.pack_id == "PL"
        assert pack.locale == "pl_PL"
        assert pack.version == "1.0"

    def test_pl_pack_has_rules_dict(self):
        pack = load_pack("PL")
        assert isinstance(pack.rules, dict)
        assert "reguly" in pack.rules
        # 19 WT rules expected
        assert len(pack.rules["reguly"]) == 19

    def test_pl_pack_has_constants(self):
        pack = load_pack("PL")
        assert isinstance(pack.constants, dict)
        assert "wt_max_area" in pack.constants
        assert pack.constants["wt_max_area"]["bathroom_m2"] == 5.0

    def test_pl_pack_has_user_overrides(self):
        pack = load_pack("PL")
        # user_rules.json has empty "reguly" list by default
        assert isinstance(pack.user_overrides, dict)


class TestLoadPackErrors:
    def test_unknown_pack_raises(self):
        with pytest.raises(CodePackError, match="not found"):
            load_pack("NONEXISTENT")

    def test_default_pack_is_pl(self):
        pack = load_pack()  # no arg
        assert pack.pack_id == "PL"
```

- [ ] **Step 2: Run test to confirm RED**

```bash
pytest tests/test_pack_loader.py -v
```

Expected: ImportError or ModuleNotFoundError (rules._loader doesn't exist yet). This is the "fails for the right reason" check.

---

### Task 6: Write `rules/_loader.py` — minimal implementation (GREEN)

**Files:**
- Create: `rules/_loader.py`

- [ ] **Step 1: Implement minimal `load_pack`**

Create `rules/_loader.py`:

```python
"""Code pack loader.

Loads a code pack from `rules/{PACK_ID}/` with manifest + rules + constants
+ user overrides. Validates against Pydantic schemas (`rules._schema`).

Usage:
    from rules._loader import load_pack
    pack = load_pack("PL")
    bathroom_max = pack.constants["wt_max_area"]["bathroom_m2"]  # 5.0
    rule_001 = next(r for r in pack.rules["reguly"] if r["id"] == "wt_001")
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from rules._schema import PackConstants, PackManifest

RULES_ROOT = Path(__file__).resolve().parent


class CodePackError(Exception):
    """Raised when a code pack is missing or invalid."""


@dataclass
class CodePack:
    """A loaded, validated code pack.

    Attributes:
        pack_id: e.g. "PL"
        locale: e.g. "pl_PL"
        version: pack version, e.g. "1.0"
        manifest: parsed PackManifest (Pydantic model)
        rules: parsed wt_rules.json content (dict with "reguly" list)
        constants: parsed constants.yaml content (dict)
        user_overrides: parsed user_rules.json content (dict)
        path: filesystem path to the pack directory
    """
    pack_id: str
    locale: str
    version: str
    manifest: PackManifest
    rules: Dict[str, Any] = field(default_factory=dict)
    constants: Dict[str, Any] = field(default_factory=dict)
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    path: Path = field(default_factory=Path)


def load_pack(pack_id: str = "PL") -> CodePack:
    """Load and validate a code pack.

    Args:
        pack_id: Pack directory name under `rules/`. Defaults to "PL".

    Returns:
        CodePack with manifest, rules, constants, user_overrides parsed.

    Raises:
        CodePackError: if pack directory is missing, manifest invalid,
            or constants fail schema validation.
    """
    pack_dir = RULES_ROOT / pack_id
    if not pack_dir.is_dir():
        raise CodePackError(
            f"Code pack '{pack_id}' not found at {pack_dir}. "
            f"Available packs: {[p.name for p in RULES_ROOT.iterdir() if p.is_dir() and not p.name.startswith('_')]}"
        )

    manifest_path = pack_dir / "pack.yaml"
    if not manifest_path.is_file():
        raise CodePackError(f"Missing pack.yaml in {pack_dir}")

    try:
        manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = PackManifest(**manifest_data)
    except (yaml.YAMLError, ValidationError) as exc:
        raise CodePackError(f"Invalid pack.yaml in {pack_dir}: {exc}") from exc

    rules_path = pack_dir / manifest.files.rules
    if not rules_path.is_file():
        raise CodePackError(f"Missing rules file: {rules_path}")
    rules = json.loads(rules_path.read_text(encoding="utf-8"))

    constants_path = pack_dir / manifest.files.constants
    constants: Dict[str, Any] = {}
    if constants_path.is_file():
        constants_data = yaml.safe_load(constants_path.read_text(encoding="utf-8"))
        try:
            PackConstants(**constants_data)  # validate
        except ValidationError as exc:
            raise CodePackError(f"Invalid constants.yaml in {pack_dir}: {exc}") from exc
        constants = constants_data

    user_overrides_path = pack_dir / manifest.files.user_overrides
    user_overrides: Dict[str, Any] = {}
    if user_overrides_path.is_file():
        user_overrides = json.loads(user_overrides_path.read_text(encoding="utf-8"))

    return CodePack(
        pack_id=manifest.code_pack_id,
        locale=manifest.locale,
        version=manifest.version,
        manifest=manifest,
        rules=rules,
        constants=constants,
        user_overrides=user_overrides,
        path=pack_dir,
    )
```

- [ ] **Step 2: Run test — first 4 cases will pass, constants test will FAIL (no constants.yaml yet)**

```bash
pytest tests/test_pack_loader.py -v
```

Expected:
- `test_load_pl_pack_returns_codepack` — PASS
- `test_pl_pack_has_rules_dict` — PASS
- `test_pl_pack_has_constants` — **FAIL** (constants.yaml doesn't exist yet — empty dict, missing "wt_max_area")
- `test_pl_pack_has_user_overrides` — PASS
- `test_unknown_pack_raises` — PASS
- `test_default_pack_is_pl` — PASS

This is the expected red. Constants test will go green in Week 2 when we create constants.yaml.

- [ ] **Step 3: Mark constants test as expected-fail (xfail) with reason**

Edit `tests/test_pack_loader.py`. Change `test_pl_pack_has_constants` to:

```python
    @pytest.mark.xfail(reason="constants.yaml not yet created — Week 2 Task 9")
    def test_pl_pack_has_constants(self):
        pack = load_pack("PL")
        assert isinstance(pack.constants, dict)
        assert "wt_max_area" in pack.constants
        assert pack.constants["wt_max_area"]["bathroom_m2"] == 5.0
```

- [ ] **Step 4: Re-run, confirm green**

```bash
pytest tests/test_pack_loader.py -v
```

Expected: 5 passed, 1 xfailed.

- [ ] **Step 5: Commit**

```bash
git add rules/_loader.py tests/test_pack_loader.py
git commit -m "feat(rules): add load_pack() with manifest + rules + user_overrides"
```

---

### Task 7: Add edge case tests for loader errors

**Files:**
- Modify: `tests/test_pack_loader.py`

- [ ] **Step 1: Add error-case tests**

Append to `tests/test_pack_loader.py`:

```python
class TestLoadPackEdgeCases:
    def test_missing_manifest_raises(self, tmp_path, monkeypatch):
        # Create a pack dir with no pack.yaml
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Missing pack.yaml"):
            load_pack("BAD")

    def test_invalid_manifest_raises(self, tmp_path, monkeypatch):
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        # Manifest missing required fields
        (bad_pack / "pack.yaml").write_text("code_pack_id: BAD\n")
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Invalid pack.yaml"):
            load_pack("BAD")

    def test_missing_rules_file_raises(self, tmp_path, monkeypatch):
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        (bad_pack / "pack.yaml").write_text("""
code_pack_id: BAD
country_code: BAD
locale: xx_XX
version: "1.0"
version_compat: ">=0.0.0"
display_name: "Bad pack"
description: "Bad"
""")
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Missing rules file"):
            load_pack("BAD")

    def test_pack_path_attribute_set(self):
        pack = load_pack("PL")
        assert pack.path.name == "PL"
        assert (pack.path / "pack.yaml").is_file()
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_pack_loader.py -v
```

Expected: 9 passed, 1 xfailed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pack_loader.py
git commit -m "test(rules): add edge case tests for load_pack errors"
```

---

### Task 8: Refactor `core/plot_verifier.py` to use `load_pack`

**Files:**
- Modify: `core/plot_verifier.py:23-37,128-135`

- [ ] **Step 1: Read current plot_verifier.py imports and constructor**

```bash
sed -n '23,40p;120,150p' core/plot_verifier.py
```

Note the structure: `RULES_DIR` constant + `__init__` reads `wt_rules.json` and `user_rules.json` from disk.

- [ ] **Step 2: Replace RULES_DIR + JSON reads with `load_pack`**

In `core/plot_verifier.py`:

Remove line 37:

```python
RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
```

Add to imports (around line 21-34):

```python
from rules._loader import load_pack
```

Find the `__init__` method (~line 100-140) that reads `wt_rules.json` + `user_rules.json`. Replace the file reading with:

```python
def __init__(self, ..., pack_id: str = "PL", ...):
    """..."""
    # OLD:
    # self._wt_rules = self._read_json(RULES_DIR / "wt_rules.json", "reguly")
    # user_overrides = [
    #     r for r in self._read_json(RULES_DIR / "user_rules.json", "reguly")
    #     ...
    # ]

    # NEW:
    pack = load_pack(pack_id)
    self._wt_rules = pack.rules.get("reguly", [])
    user_overrides_raw = pack.user_overrides.get("reguly", [])
    # ... apply existing user_overrides processing logic to user_overrides_raw
```

(Read the actual existing logic in `plot_verifier.py:120-150` before making the edit; preserve its semantics.)

- [ ] **Step 3: Remove `_read_json` helper if no longer used**

```bash
grep -n "_read_json" core/plot_verifier.py
```

If only the `__init__` referenced it, remove the helper method.

- [ ] **Step 4: Run plot_verifier tests**

```bash
pytest tests/test_plot_verifier.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Run full non-GUI suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: 144 passed (no regressions).

- [ ] **Step 6: Commit**

```bash
git add core/plot_verifier.py
git commit -m "refactor(plot_verifier): load rules via rules._loader.load_pack"
```

---

### Task 9: Write `rules/README.md` — "How to add a country pack"

**Files:**
- Create: `rules/README.md`

- [ ] **Step 1: Write the documentation**

Create `rules/README.md`:

```markdown
# Code Packs

Code packs hold country-specific rules + constants. The reference pack is
`rules/PL/` (Polska, WT 2002).

## Pack structure

```
rules/{PACK_ID}/
├── pack.yaml          # Manifest (id, version, locale, references, file list)
├── wt_rules.json      # Verifier rules (analogous to PL's wt_rules.json)
├── constants.yaml     # Rule-driven constants (extracted from config.py)
└── user_rules.json    # User MPZP overrides (default: empty list)
```

## Manifest schema (`pack.yaml`)

Validated by `rules._schema.PackManifest`:

| Field | Required | Description |
|---|---|---|
| `code_pack_id` | yes | Pack ID, e.g. "PL", "UK" |
| `country_code` | yes | ISO country code |
| `locale` | yes | POSIX locale, e.g. `pl_PL` |
| `version` | yes | Pack version (semver-ish) |
| `version_compat` | yes | FloorPlan6 version range |
| `display_name` | yes | Human-readable PL name |
| `display_name_en` | no | English fallback |
| `description` | yes | One-line description |
| `references` | no | Legal/regulatory references |
| `files` | no | File mapping (defaults to standard names) |

## Constants schema (`constants.yaml`)

Validated by `rules._schema.PackConstants`. **All keys required** — see
`rules/_schema.py` for the full list. Adding a new constant requires:

1. Add field to `PackConstants` model
2. Add value to every existing pack's `constants.yaml` (or set default)
3. Update consuming code to read from `pack.constants[...]`

## Adding a new pack (e.g. UK)

1. Copy `rules/PL/` to `rules/UK/`
2. Edit `rules/UK/pack.yaml`: change `code_pack_id`, `locale`, `version`,
   `display_name`, `references` (to UK Building Regulations citations)
3. Translate/adapt `wt_rules.json` to UK BR equivalents (rule IDs typically
   prefixed `uk_001`, `uk_002`, ...)
4. Adapt `constants.yaml` (UK uses different setbacks, FAR vs WIZ, etc.)
5. Validate: `python -c "from rules._loader import load_pack; load_pack('UK')"`
6. Add tests: copy `tests/test_pack_loader.py::TestLoadPackHappyPath` patterns

## Loading a pack at runtime

```python
from rules._loader import load_pack

pack = load_pack("PL")  # default
pack.rules                # parsed wt_rules.json
pack.constants            # parsed constants.yaml dict
pack.constants["wt_max_area"]["bathroom_m2"]  # 5.0
pack.user_overrides       # parsed user_rules.json
pack.manifest             # Pydantic PackManifest model
pack.path                 # Path to rules/PL/
```

## Constraints (NOT implemented yet, by design)

- **NO runtime hot-swap** between packs — load once at session start
- **NO generic constraint engine** — F1-F10 stay hardcoded in solver/validator
- **NO i18n in pack** — locale string is metadata only, UI translation is
  separate concern (Phase 3+)
```

- [ ] **Step 2: Commit**

```bash
git add rules/README.md
git commit -m "docs(rules): add README explaining code pack structure"
```

---

## Week 1 milestone

After Tasks 1-9:
- `rules/PL/` exists with `pack.yaml`, `wt_rules.json`, `user_rules.json`
- `rules/_loader.py` + `rules/_schema.py` work
- `core/plot_verifier.py` uses `load_pack`
- `tests/test_pack_loader.py` has 9 passing + 1 xfail
- All 144 existing tests still green

**Verification:**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
python -c "
from rules._loader import load_pack
p = load_pack('PL')
print(f'Pack: {p.pack_id} v{p.version}, {len(p.rules[\"reguly\"])} rules')
"
```

Expected:
- pytest: ~150 passed (144 existing + 9 new + 1 xfail)
- Output: `Pack: PL v1.0, 19 rules`

---

## Week 2 — Constants Migration

### Task 10: Create `rules/PL/constants.yaml`

**Files:**
- Create: `rules/PL/constants.yaml`
- Create: `tests/test_pack_constants.py`

- [ ] **Step 1: Read all rule-driven constants from `config.py`**

```bash
cat config.py
```

Note all WT_*, HUB_*, APARTMENT_*, ORIENTATION_*, DEFAULT_SCORER_WEIGHTS, WALL_THICKNESS_*, PROPORTION_*, FLOOR_RESERVE_RATIO, DOOR_MIN_WIDTH constants.

- [ ] **Step 2: Create `rules/PL/constants.yaml`**

```yaml
# Rule-driven constants extracted from config.py.
# See rules/_schema.py PackConstants for the schema.

# === WT 2002 — area/width limits per room type ===
wt_min_area:
  salon_kawalerka: 25.0
  salon: 16.0
  sypialnia_2os: 9.0
  sypialnia_1os: 6.0
  kuchnia: 6.0
  aneks_kuchenny: 4.0
  lazienka_wanna: 4.5
  lazienka_prysznic: 2.5
  wc: 1.5
  hub: 0.0

wt_max_area:
  bathroom_m2: 5.0
  wc_m2: 3.0
  # Legacy room-prefix keys (used by validator startswith match):
  lazienka: 5.0

wt_min_width:
  salon: 3.2
  sypialnia_2os: 2.4
  sypialnia_1os: 2.0
  kuchnia: 2.4
  lazienka: 1.5
  wc: 1.0
  hub: 1.2

# === Setbacks (defaults when MPZP doesn't specify) ===
setback_defaults:
  front_m: 6.0
  side_m: 4.0
  rear_m: 4.0
  well_to_boundary_m: 7.5

# === Hub ===
hub_min_percent:
  M1: 0.08
  M2: 0.10
  M3: 0.10
  M4: 0.12
  M5: 0.12
hub_max_percent: 0.15
hub_min_area:
  M1: 4.0
  M2: 5.0
  M3: 6.0
  M4: 8.0
  M5: 10.0

# === Apartment types (Stage 3) ===
apartment_min_area:
  M1: 35.0
  M2: 45.0
  M3: 60.0
  M4: 80.0
  M5: 100.0
apartment_opt_area:
  M1: 40.0
  M2: 55.0
  M3: 75.0
  M4: 100.0
  M5: 130.0
apartment_max_aspect: 3.0
apartment_mix_default:
  M1: 0.10
  M2: 0.30
  M3: 0.40
  M4: 0.10
  M5: 0.10

# === Building height class (WT, dział VI) ===
building_class:
  N_max_height_m: 12.0
  SW_max_height_m: 25.0
  W_max_height_m: 55.0
  WW_above_m: 55.0

# === Corridors + escape ===
wt_corridor_internal_min: 1.2
wt_corridor_public_min: 1.4
wt_dojscie_max_1klatka: 10.0
wt_dojscie_max_2klatki: 40.0
door_min_width: 0.9

# === Stairs ===
wt_stair_bieg_width: 0.9
wt_stair_spocznik_width: 1.2
wt_stair_step_height_max: 0.16
wt_stair_blondel: 0.63
wt_stair_step_width_min: 0.25

# === Elevator ===
wt_elevator_height_threshold: 9.5
wt_elevator_shaft_w: 1.5
wt_elevator_shaft_l: 1.7
wt_elevator_fire_w: 2.0
wt_elevator_fire_l: 2.4

# === Wall thicknesses ===
wall_thickness_structural: 0.24
wall_thickness_partition: 0.12
wall_thickness_bathroom: 0.10

# === Proportions ===
proportion_optimal: 1.3
proportion_max: 2.0
proportion_absolute_max: 2.5

# === Orientation quality ===
orientation_quality:
  S: 1.0
  SW: 0.95
  SE: 0.90
  W: 0.85
  E: 0.80
  NW: 0.65
  NE: 0.60
  N: 0.50

# === Scorer weights (defaults; can be overridden by dataset_stats) ===
default_scorer_weights:
  proporcje_pokoi: 0.25
  efektywnosc_huba: 0.20
  orientacja_salonu: 0.15
  powierzchnia_uzytkowa: 0.15
  separacja_stref: 0.15
  regularnosc_geometrii: 0.10

# === Floor mode ===
floor_reserve_ratio: 0.15

# === Parking ===
parking_ratio_per_unit: 1.5

# === Mode B (Stage 1 subdivision) ===
min_subplot_front_m: 18.0

# === Przedsionek (vestibule) depth per building class ===
wt_przedsionek_depth:
  N: 0.0
  SW: 1.0
  W: 1.5
  WW: 1.5
```

- [ ] **Step 3: Validate against schema**

```bash
python -c "
import yaml
from rules._schema import PackConstants
data = yaml.safe_load(open('rules/PL/constants.yaml'))
PackConstants(**data)
print('OK: constants.yaml validates')
"
```

Expected: `OK: constants.yaml validates`. If ValidationError, fix the YAML (likely missing key — the error will say which).

- [ ] **Step 4: Remove the xfail marker from constants test**

Edit `tests/test_pack_loader.py` — remove the `@pytest.mark.xfail` decorator from `test_pl_pack_has_constants`.

- [ ] **Step 5: Run loader tests**

```bash
pytest tests/test_pack_loader.py -v
```

Expected: 10 passed (no xfailed).

- [ ] **Step 6: Commit**

```bash
git add rules/PL/constants.yaml tests/test_pack_loader.py
git commit -m "feat(rules): add PL constants.yaml with all rule-driven values from config.py"
```

---

### Task 11: Write dedicated `tests/test_pack_constants.py`

**Files:**
- Create: `tests/test_pack_constants.py`

- [ ] **Step 1: Write tests for constants completeness**

Create `tests/test_pack_constants.py`:

```python
"""Tests asserting PL constants.yaml contains all values needed by code.

This is a contract check: when refactoring config.py, this guarantees the
constants are present in the pack BEFORE we delete them from config.py.
"""
from __future__ import annotations

import pytest

from rules._loader import load_pack


@pytest.fixture(scope="module")
def pl_pack():
    return load_pack("PL")


class TestWTAreas:
    def test_bathroom_max(self, pl_pack):
        assert pl_pack.constants["wt_max_area"]["bathroom_m2"] == 5.0

    def test_wc_max(self, pl_pack):
        assert pl_pack.constants["wt_max_area"]["wc_m2"] == 3.0

    def test_min_areas_have_all_room_types(self, pl_pack):
        expected = {"salon_kawalerka", "salon", "sypialnia_2os", "sypialnia_1os",
                    "kuchnia", "aneks_kuchenny", "lazienka_wanna", "lazienka_prysznic",
                    "wc", "hub"}
        assert set(pl_pack.constants["wt_min_area"].keys()) == expected


class TestHub:
    def test_hub_max_percent(self, pl_pack):
        assert pl_pack.constants["hub_max_percent"] == 0.15

    def test_hub_min_percent_keys(self, pl_pack):
        assert set(pl_pack.constants["hub_min_percent"].keys()) == {"M1", "M2", "M3", "M4", "M5"}


class TestApartments:
    def test_apartment_min_area_m1(self, pl_pack):
        assert pl_pack.constants["apartment_min_area"]["M1"] == 35.0

    def test_apartment_mix_sums_to_one(self, pl_pack):
        mix = pl_pack.constants["apartment_mix_default"]
        assert abs(sum(mix.values()) - 1.0) < 1e-9


class TestBuildingClass:
    def test_thresholds(self, pl_pack):
        bc = pl_pack.constants["building_class"]
        assert bc["N_max_height_m"] == 12.0
        assert bc["SW_max_height_m"] == 25.0
        assert bc["W_max_height_m"] == 55.0


class TestCorridors:
    def test_public_corridor(self, pl_pack):
        assert pl_pack.constants["wt_corridor_public_min"] == 1.4

    def test_internal_corridor(self, pl_pack):
        assert pl_pack.constants["wt_corridor_internal_min"] == 1.2


class TestProportions:
    def test_proportion_absolute_max(self, pl_pack):
        assert pl_pack.constants["proportion_absolute_max"] == 2.5


class TestOrientationQuality:
    def test_south_is_max(self, pl_pack):
        oq = pl_pack.constants["orientation_quality"]
        assert oq["S"] == 1.0

    def test_north_is_min(self, pl_pack):
        oq = pl_pack.constants["orientation_quality"]
        assert oq["N"] == 0.50


class TestModeBSubdivision:
    def test_min_subplot_front(self, pl_pack):
        assert pl_pack.constants["min_subplot_front_m"] == 18.0
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_pack_constants.py -v
```

Expected: ~12 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pack_constants.py
git commit -m "test(rules): assert PL constants.yaml has all required keys + values"
```

---

### Task 12: Set up shared pack instance for code modules

**Files:**
- Modify: `rules/_loader.py` (add `get_default_pack()`)

- [ ] **Step 1: Add a memoized default pack accessor**

Append to `rules/_loader.py`:

```python
_default_pack: CodePack | None = None


def get_default_pack() -> CodePack:
    """Return the default code pack (PL), memoized for the process lifetime.

    Use this in core modules that need pack constants but don't take a pack
    argument. To use a different pack, call `set_default_pack(load_pack("UK"))`
    at session start (Phase 2+ feature).
    """
    global _default_pack
    if _default_pack is None:
        _default_pack = load_pack("PL")
    return _default_pack


def set_default_pack(pack: CodePack) -> None:
    """Replace the memoized default pack. Call at session start only."""
    global _default_pack
    _default_pack = pack


def reset_default_pack() -> None:
    """Clear the memoized default pack. For tests."""
    global _default_pack
    _default_pack = None
```

- [ ] **Step 2: Add a test for the memoization**

Append to `tests/test_pack_loader.py`:

```python
class TestDefaultPack:
    def test_default_pack_is_memoized(self):
        from rules._loader import get_default_pack, reset_default_pack
        reset_default_pack()
        p1 = get_default_pack()
        p2 = get_default_pack()
        assert p1 is p2  # same instance

    def test_set_default_pack_overrides(self):
        from rules._loader import get_default_pack, set_default_pack, reset_default_pack
        reset_default_pack()
        original = get_default_pack()
        # Setting a different pack would be: set_default_pack(load_pack("UK"))
        # Here we just verify the setter mechanism with the same pack
        set_default_pack(original)
        assert get_default_pack() is original
        reset_default_pack()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_pack_loader.py -v
```

Expected: 12 passed.

- [ ] **Step 4: Commit**

```bash
git add rules/_loader.py tests/test_pack_loader.py
git commit -m "feat(rules): add get_default_pack() memoized accessor"
```

---

### Task 13: Refactor `core/cpsat_solver.py` to use pack constants

**Files:**
- Modify: `core/cpsat_solver.py` (imports + constant refs)

- [ ] **Step 1: Find all config imports in cpsat_solver.py**

```bash
grep -n "from config import\|^from config\|config\\." core/cpsat_solver.py
```

Note which constants are imported.

- [ ] **Step 2: Replace imports with pack accessor**

In `core/cpsat_solver.py`:

```python
# OLD (likely at top of file):
from config import WT_MIN_AREA, WT_MAX_AREA, WT_MIN_WIDTH, HUB_MIN_PERCENT, HUB_MAX_PERCENT, HUB_MIN_AREA, ORIENTATION_QUALITY

# NEW:
from rules._loader import get_default_pack

_PACK = get_default_pack()
WT_MIN_AREA = _PACK.constants["wt_min_area"]
WT_MAX_AREA = _PACK.constants["wt_max_area"]
WT_MIN_WIDTH = _PACK.constants["wt_min_width"]
HUB_MIN_PERCENT = _PACK.constants["hub_min_percent"]
HUB_MAX_PERCENT = _PACK.constants["hub_max_percent"]
HUB_MIN_AREA = _PACK.constants["hub_min_area"]
ORIENTATION_QUALITY = _PACK.constants["orientation_quality"]
```

This pattern preserves the **same names** the rest of the module uses, so we don't need to touch the solver logic.

- [ ] **Step 3: Run cpsat_solver-related tests**

```bash
pytest tests/ --ignore=tests/test_gui.py -k "solver or stage4 or cpsat" -q
```

Expected: all relevant tests pass.

- [ ] **Step 4: Run full suite to catch any regressions**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: same total as before (~152 passed including new pack tests).

- [ ] **Step 5: Commit**

```bash
git add core/cpsat_solver.py
git commit -m "refactor(cpsat_solver): load WT/HUB/orientation constants from pack"
```

---

### Task 14: Refactor `core/validator.py`

**Files:**
- Modify: `core/validator.py`

- [ ] **Step 1: Find config imports**

```bash
grep -n "from config import\|config\\." core/validator.py
```

- [ ] **Step 2: Replace with pack accessor (same pattern as Task 13)**

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
WT_MAX_AREA = _PACK.constants["wt_max_area"]
PROPORTION_OPTIMAL = _PACK.constants["proportion_optimal"]
PROPORTION_MAX = _PACK.constants["proportion_max"]
PROPORTION_ABSOLUTE_MAX = _PACK.constants["proportion_absolute_max"]
# ... add other constants validator imports
```

- [ ] **Step 3: Run validator tests**

```bash
pytest tests/ --ignore=tests/test_gui.py -k "validator or stage4" -q
```

Expected: pass.

- [ ] **Step 4: Run full suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: same as Task 13 step 4.

- [ ] **Step 5: Commit**

```bash
git add core/validator.py
git commit -m "refactor(validator): load proportion + WT_MAX constants from pack"
```

---

### Task 15: Refactor `core/scorer.py`

**Files:**
- Modify: `core/scorer.py`

- [ ] **Step 1: Find config imports**

```bash
grep -n "from config import\|config\\." core/scorer.py
```

- [ ] **Step 2: Replace with pack pattern**

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
DEFAULT_SCORER_WEIGHTS = _PACK.constants["default_scorer_weights"]
ORIENTATION_QUALITY = _PACK.constants["orientation_quality"]
```

- [ ] **Step 3: Run scorer tests**

```bash
pytest tests/ --ignore=tests/test_gui.py -k "scorer or stage4" -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add core/scorer.py
git commit -m "refactor(scorer): load weights + orientation from pack"
```

---

### Task 16: Refactor `core/site_planner.py` and `core/plot_indicators.py`

**Files:**
- Modify: `core/site_planner.py`
- Modify: `core/plot_indicators.py`

- [ ] **Step 1: Find config imports in both**

```bash
grep -n "from config import\|config\\." core/site_planner.py core/plot_indicators.py
```

- [ ] **Step 2: Replace with pack pattern in `core/site_planner.py`**

Add at top of file:

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
# Map each config import → pack constant. Common ones for site_planner:
PARKING_RATIO_PER_UNIT = _PACK.constants["parking_ratio_per_unit"]
SETBACK_DEFAULTS = _PACK.constants["setback_defaults"]
MIN_SUBPLOT_FRONT_M = _PACK.constants["min_subplot_front_m"]
```

(Verify against actual `from config import ...` line.)

- [ ] **Step 3: Same for `core/plot_indicators.py`**

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
PARKING_RATIO_PER_UNIT = _PACK.constants["parking_ratio_per_unit"]
```

- [ ] **Step 4: Run Stage 1 tests**

```bash
pytest tests/test_site_planner.py tests/test_plot_verifier.py tests/test_buildable_zone.py -v
```

Expected: 44 passed (12 + 14 + 18).

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: same total.

- [ ] **Step 6: Commit**

```bash
git add core/site_planner.py core/plot_indicators.py
git commit -m "refactor(site_planner, plot_indicators): load constants from pack"
```

---

### Task 17: Refactor `core/floor_compute.py`, `floor_validation.py`, `floor_layout.py`

**Files:**
- Modify: `core/floor_compute.py`
- Modify: `core/floor_validation.py`
- Modify: `core/floor_layout.py`

- [ ] **Step 1: Find config imports in all three**

```bash
grep -n "from config import\|config\\." core/floor_compute.py core/floor_validation.py core/floor_layout.py
```

- [ ] **Step 2: Replace each file's imports with pack pattern**

For `core/floor_compute.py`:

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
APARTMENT_MIN_AREA = _PACK.constants["apartment_min_area"]
APARTMENT_OPT_AREA = _PACK.constants["apartment_opt_area"]
WT_BUILDING_CLASS_THRESHOLDS = {
    "N": _PACK.constants["building_class"]["N_max_height_m"],
    "SW": _PACK.constants["building_class"]["SW_max_height_m"],
    "W": _PACK.constants["building_class"]["W_max_height_m"],
}
WT_STAIR_BIEG_WIDTH = _PACK.constants["wt_stair_bieg_width"]
WT_STAIR_SPOCZNIK_WIDTH = _PACK.constants["wt_stair_spocznik_width"]
WT_ELEVATOR_HEIGHT_THRESHOLD = _PACK.constants["wt_elevator_height_threshold"]
WT_ELEVATOR_SHAFT_W = _PACK.constants["wt_elevator_shaft_w"]
WT_ELEVATOR_SHAFT_L = _PACK.constants["wt_elevator_shaft_l"]
# ... etc, mirror config.py imports
```

For `core/floor_validation.py`:

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
WT_CORRIDOR_INTERNAL_MIN = _PACK.constants["wt_corridor_internal_min"]
WT_CORRIDOR_PUBLIC_MIN = _PACK.constants["wt_corridor_public_min"]
WT_DOJSCIE_MAX_1KLATKA = _PACK.constants["wt_dojscie_max_1klatka"]
WT_DOJSCIE_MAX_2KLATKI = _PACK.constants["wt_dojscie_max_2klatki"]
DOOR_MIN_WIDTH = _PACK.constants["door_min_width"]
```

For `core/floor_layout.py`:

```python
from rules._loader import get_default_pack

_PACK = get_default_pack()
APARTMENT_MIX_DEFAULT = _PACK.constants["apartment_mix_default"]
FLOOR_RESERVE_RATIO = _PACK.constants["floor_reserve_ratio"]
APARTMENT_MAX_ASPECT = _PACK.constants["apartment_max_aspect"]
WT_CORRIDOR_PUBLIC_MIN = _PACK.constants["wt_corridor_public_min"]
```

- [ ] **Step 3: Run floor (Stage 3) tests**

```bash
pytest tests/ --ignore=tests/test_gui.py -k "floor or stage3" -q
```

Expected: pass.

- [ ] **Step 4: Run full suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: same total.

- [ ] **Step 5: Commit**

```bash
git add core/floor_compute.py core/floor_validation.py core/floor_layout.py
git commit -m "refactor(floor): load building class + corridor + apartment constants from pack"
```

---

### Task 18: Find and refactor any remaining `from config import` statements

**Files:**
- Modify: any remaining file with `from config import`

- [ ] **Step 1: Search the whole codebase for `from config import`**

```bash
grep -rn "from config import\|^import config\|config\\.[A-Z]" \
  --include="*.py" \
  --exclude-dir=__pycache__ \
  --exclude-dir=notebooks \
  --exclude-dir=.git \
  /Users/dawidcwiertniewicz/Desktop/claude\ code/FloorPlan6/
```

Expected: only `WALL_THICKNESS_*` (still in config.py — those are physical/runtime, NOT rule-driven, can stay) and possibly leftover Python-runtime constants. **Note:** `wall_thickness_*` IS in `constants.yaml` (it's physical but tied to WT regulation thickness specs) — decision: keep it in pack since it's used by solver in connection with WT compliance.

- [ ] **Step 2: Refactor any remaining imports**

For each remaining `from config import X` in core/, ui/, bridge/, viz/:
- If `X` is a rule-driven constant → replace via `get_default_pack().constants[...]`
- If `X` is Python-runtime (e.g. `SCALE`) → leave it in `config.py`

- [ ] **Step 3: Run full suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: ~158 passed.

- [ ] **Step 4: Commit (if any changes)**

```bash
git add -u
git commit -m "refactor: complete config → pack migration in remaining modules"
```

---

### Task 19: Cleanup `config.py` — remove migrated constants

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Determine what stays in config.py**

After all refactors, `config.py` should keep ONLY:
- Python-runtime constants that are NOT rule-driven (e.g. SCALE if you have one)
- Module docstring updated to reflect new role

If everything has been migrated, the file may be reduced to ~10 lines or deleted entirely. Check if any imports remain:

```bash
grep -rn "from config import\|^import config" --include="*.py" .
```

- [ ] **Step 2: Edit `config.py` to keep ONLY non-rule-driven constants**

Replace `config.py` with:

```python
"""FloorPlan6 — Python-runtime constants (NOT rule-driven).

Rule-driven constants (WT_*, HUB_*, APARTMENT_*, etc.) live in
`rules/{PACK_ID}/constants.yaml` and are loaded via `rules._loader.load_pack`.

This module retains ONLY constants that are tied to the Python implementation
itself (precision scale, sentinel values), not to any architectural code.
"""
from __future__ import annotations

# CP-SAT solver works in centimeters (integer). Multiply meters by SCALE.
SCALE = 100  # cm per m
```

(Adjust if you have other true Python-runtime constants.)

- [ ] **Step 3: Verify no remaining imports break**

```bash
grep -rn "from config import\|^import config" --include="*.py" .
```

If anything imports a removed constant, fix it (move to pack accessor).

- [ ] **Step 4: Run full suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -q
```

Expected: ~158 passed (no regressions).

- [ ] **Step 5: Verify config.py is < 50 lines**

```bash
wc -l config.py
```

Expected: < 50.

- [ ] **Step 6: Commit**

```bash
git add config.py
git commit -m "refactor(config): cleanup — remove all rule-driven constants migrated to rules/PL/"
```

---

### Task 20: Update `docs/STATE.md` with Phase 1 completion

**Files:**
- Modify: `docs/STATE.md`

- [ ] **Step 1: Append Phase 1 section to STATE.md**

Edit `docs/STATE.md`. Find the "What's next" section and add above it:

```markdown
### Stage 1 — Phase 1 (Pack Architecture) — COMPLETED 2026-MM-DD

| Component | Status |
|---|---|
| `rules/_loader.py` | ✅ `load_pack()` + `get_default_pack()` (memoized) |
| `rules/_schema.py` | ✅ Pydantic schemas (PackManifest, PackConstants) |
| `rules/PL/pack.yaml` | ✅ PL pack manifest (v1.0) |
| `rules/PL/constants.yaml` | ✅ All rule-driven constants extracted from config.py |
| `rules/PL/wt_rules.json` | ✅ 19 WT 2002 rules (moved from rules/) |
| `rules/PL/user_rules.json` | ✅ User MPZP overrides template (moved) |
| `rules/README.md` | ✅ "How to add a country pack" |
| `tests/test_pack_loader.py` | ✅ 12 tests pass |
| `tests/test_pack_constants.py` | ✅ ~12 tests pass |
| `core/cpsat_solver.py`, `validator.py`, `scorer.py`, `site_planner.py`, `plot_indicators.py`, `floor_*.py` | ✅ All load constants from pack |
| `config.py` | ✅ Reduced to <50 lines (SCALE only) |

**Tests:** ~158 passed, 30 skipped, 1 xpassed.
**Behavior change:** none — pure refactor.
**Next:** Phase 2 — Report Layer (PDF generation).
```

(Replace `MM-DD` with actual completion date.)

- [ ] **Step 2: Commit**

```bash
git add docs/STATE.md
git commit -m "docs(STATE): mark Stage 1 Phase 1 (pack architecture) complete"
```

---

### Task 21: Final verification before merge

**Files:** none

- [ ] **Step 1: Run the entire non-GUI test suite**

```bash
pytest tests/ --ignore=tests/test_gui.py -v --tb=short
```

Expected: all green, ~158 passed total.

- [ ] **Step 2: Verify `config.py` has only Python-runtime constants**

```bash
cat config.py
wc -l config.py
```

Expected: <50 lines, only SCALE (and possibly 1-2 others if needed).

- [ ] **Step 3: Verify `rules/PL/` structure complete**

```bash
ls -la rules/PL/
test -f rules/PL/pack.yaml && echo "manifest OK"
test -f rules/PL/constants.yaml && echo "constants OK"
test -f rules/PL/wt_rules.json && echo "rules OK"
test -f rules/PL/user_rules.json && echo "user rules OK"
```

Expected: 4 files, all "OK" prints.

- [ ] **Step 4: Verify `rules/_loader.py` works end-to-end**

```bash
python -c "
from rules._loader import load_pack, get_default_pack
p = load_pack('PL')
assert p.pack_id == 'PL'
assert p.version == '1.0'
assert len(p.rules['reguly']) == 19
assert p.constants['wt_max_area']['bathroom_m2'] == 5.0
print('Pack PL loaded:', p.pack_id, 'v' + p.version)
print('Constants:', len(p.constants), 'top-level keys')
print('Rules:', len(p.rules['reguly']))
"
```

Expected:
```
Pack PL loaded: PL v1.0
Constants: ~30 top-level keys
Rules: 19
```

- [ ] **Step 5: Optional — push branch + open PR**

```bash
git push -u origin feature/stage1-phase1-pack-architecture
gh pr create --title "Stage 1 Phase 1: Pack Architecture" --body "$(cat <<'EOF'
## Summary
- Modularna architektura code-pack: `rules/PL/` jako proof of concept
- `rules/_loader.py` + Pydantic schema validation
- Wszystkie rule-driven constants z `config.py` przeniesione do `rules/PL/constants.yaml`
- Wszystkie core modules ładują constants przez `get_default_pack()`
- `config.py` zredukowany do <50 linii (SCALE only)

## Test plan
- [x] `pytest tests/ --ignore=tests/test_gui.py` — ~158 zielonych
- [x] `python -c "from rules._loader import load_pack; p = load_pack('PL')"` — działa
- [x] `wc -l config.py` — <50 linii
- [x] Brak regresji w Stage 4 (cpsat solver) ani Stage 3 (floor)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

(Skip PR creation if you prefer to merge locally or work in main.)

---

## Phase 1 Complete

After all 21 tasks:
- ✅ `rules/PL/` pack architecture in place
- ✅ All constants migrated from `config.py` to `rules/PL/constants.yaml`
- ✅ All core modules use `get_default_pack().constants[...]`
- ✅ ~158 tests passing (144 original + ~14 new pack tests)
- ✅ Zero behavior changes — pure refactor

**Ready for Phase 2:** Report Layer (data + renderer + PDF assembly).

---

## Open questions deferred to during implementation

1. **`wall_thickness_*` constants**: marked as physical-runtime in some readings, but they're WT-derived (regulation specifies wall thicknesses for fire/insulation classes). Current plan: keep in `constants.yaml` since they're WT-tied. Reconsider only if a non-PL pack would have radically different values.

2. **`WT_PRZEDSIONEK_DEPTH` keying**: PL uses building class strings ("N", "SW", "W", "WW"). UK BR may use different keys. Current schema uses `Dict[str, float]` — flexible enough for now.

3. **`STATUS_ICON` and `STATUS_COLOR` in `plot_verifier.py`**: hardcoded emoji/hex strings. Could be moved to `constants.yaml` but are UI-presentation, not rule-driven. **Decision: leave hardcoded** for Phase 1, revisit in Phase 3 (UI work).
