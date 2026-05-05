# LESSONS_LEARNED — patterns to reuse + mistakes to avoid

> **Goal:** collect proven patterns from FloorPlan2 (PyQt5+heuristics),
> FloorPlan4 Python (CP-SAT, 36/36 tests pass) and FloorPlan4_CPP (Stage 1
> MPZP + Plot Subdivision). We do NOT copy blindly. Each pattern requires
> deciding whether it fits FloorPlan6.

---

## SOURCES

| Project | Location | Status | Language | What it gave |
|---------|----------|--------|----------|--------------|
| FloorPlan2 | `claude code/FloorPlan2/floor_plan_generator/` | Abandoned | Python 3.10 PyQt5 + Shapely + NetworkX | Heuristics, early visualisation |
| FloorPlan4 (Python) | `claude code/FloorPlan4/` | Abandoned 2026-04-26 | Python 3.10 OR-Tools CP-SAT + Shapely | **36/36 tests pass, 27 parameterised plans with adjacency graph** |
| FloorPlan4_CPP | `claude code/FloorPlan4_CPP/` | **Retained as UI/AC bridge reference** | C++20 OR-Tools + ACAPI | Stage 3 Floor mode works, Stage 1 MPZP analyser numerically works, **bathroom 13 m² and Plot Subdivider buggy — abandoned** |
| FloorPlan5 | `claude code/FloorPlan5/` | Documentation only | — | Strategy + rules (consolidated here) |
| **FloorPlan6** | `claude code/FloorPlan6/` | **Active** | Python 3.10 OR-Tools + Shapely + matplotlib | This repo |

---

## 5 PATTERNS WORTH REUSING

### W1 — Coverage equality `==` (zero-gap guarantee)
**Source:** FloorPlan4 Python `core/cpsat_solver.py:140` —
`model.add(sum(areas) == usable_area_cm2)`

**What it gives:** mathematical guarantee that the rooms fill the entire
outline. No holes, no overflow.

**Reuse?** YES for apartment floor plans — **already in the copied code**.
Verify it has not been changed to `<=` after copying. **However:** for small
outlines (M1 5.75×6) it may produce INFEASIBLE — need a fallback (e.g.
different template, smaller hub).

**Decision before use:** is our specific case "fill a polygon with rooms"
(YES → equality) or "place objects with possible gaps" (NO → inequality).

---

### W2 — Scale=100 (centimetres instead of metres)
**Source:** FloorPlan4 Python `core/cpsat_solver.py` constants.

**What it gives:** all CP-SAT values are integer cm — zero floating-point
rounding. Eliminates a class of bugs like "0.999 != 1.0".

**Reuse?** YES, absolutely. Already in the code. Do NOT go back to floats.

---

### W3 — Topology blocking for variant deduplication
**Source:** FloorPlan4 Python `core/variant_generator.py` lines ~95-110.

**What it gives:** after finding one variant the solver receives a
constraint "living room NOT in this quadrant" → next call generates a
different layout. We get 5 different variants instead of 5 nearly identical.

**Reuse?** YES for floor plans (variant generation). Not needed for
plot/mass generation.

---

### W4 — Axis-aligned notch detection
**Source:** FloorPlan4 Python `core/boundary_analyzer.py` — `_detect_notch()`.

**What it gives:** L-shape / U-shape detection: `bbox.difference(polygon)
== rectangle`? Then this rectangle is a "notch" treated as an obstacle in
the solver.

**Reuse?** YES for floor plans and apartment layouts. Plots are rarely
L-shape, but the algorithm works.

---

### W5 — Trapezoid handler — inscribed_rect + stretch + clip
**Source:** FloorPlan4 Python `core/trapezoid_handler.py`.

**What it gives:** for trapezoidal outlines:
1. Inscribe the largest rectangle (`inscribed_rectangle`)
2. Solver works on the rectangle (simple, works)
3. Stretch boundary rooms to the slope (linear interpolation)
4. Final clip via Shapely intersection

**Reuse?** YES for floor plans. **Already in the code as `core/trapezoid_handler.py`**.

---

### W6 — Set of 27 parameterised floor plans (`data/plans/`)
**Source:** FloorPlan4 Python `data/plans/PL_*.json`.

**What it gives:** 27 real Polish apartments with room geometry (polygons),
facades, stretch flags, **filled adjacency graph** (room_a_idx, room_b_idx,
edge_type), entry_position. Reference dataset for solver and template
selector validation.

**Reuse?** YES, absolutely. Already copied to `FloorPlan6/data/plans/`. See
`docs/TEMPLATES_GUIDE.md` for details.

---

## 6 MISTAKES TO AVOID

### E1 — Do NOT use `absorbUncoveredPolygon`
**What it was:** "fill holes" function that assigned uncovered cells to the
nearest room as `extra_rect`.

**Why bad:**
- In FloorPlan4_CPP session 2026-04-25 → "rectangles from nowhere"
  (`extra_rect` detached from the main room)
- Architecturally unacceptable (a room cannot have detached parts)
- In FloorPlan4 Python this function is ABSENT — it wasn't needed because
  Coverage equality guarantees 100 %

**Conclusion:** if Coverage equality works → you don't need absorb. If you
use inequality → you HAVE an architectural problem, don't fix it with
absorb.

---

### E2 — Do NOT lower MIN_SHARED_EDGE below 90 cm
**What it was:** attempts to change 90 cm → 50 cm/60 cm to make the solver
find a solution.

**Why bad:** 90 cm is the **standard door width**. Below = doors don't open.
This is not a tuning threshold — it's the physical size of a door.

**Conclusion:** 90 cm stays. If solver INFEASIBLE → change the template,
not the threshold.

---

### E3 — Do NOT change Coverage from `==` to `<=`
**What it was:** in C++ session 2026-04-25 I changed it to `<=` to give
M1 5.75×6 some slack.

**Why bad:** caused 15 % "holes" in the polygon. Breaks F1 (100 % coverage).

**Conclusion:** if equality is INFEASIBLE → the problem is in the template
or `min_szerokosc`, not in the constraint.

---

### E4 — Do NOT iterate a patch more than 2× in the same area
**What it was:** in C++ session 2026-04-25 → 14 patches to pre-assign cells,
3 patches to facade threshold, 2 patches to bathroom cap.

**Why bad:** every iteration introduced a regression. Patching does not fix
root causes.

**Conclusion:** **2 fails = STOP, rewrite the module.** Rule B1.

---

### E5 — Do NOT make the hub a spine/corridor
**What it was:** FloorPlan2 sometimes produced the hub as a narrow long
strip across the entire apartment.

**Why bad:** the hub is a hallway, not a corridor. Architecturally a
different element.

**Conclusion:** hub max 60 % BW, max 60 % BH, aspect ≤ 1.5. Hard constraint
in the solver. See F4.

---

### E6 — Do NOT write a geometric algorithm directly in C++ without a Python prototype
**What it was:** in C++ FloorPlan4_CPP session 2026-04-29 — Plot Subdivider
from scratch in C++. 4 known bugs after one session (sub-plots overflow
boundary, roads overflow, building zone ignored, 36 zones inserted where
~10 fit).

**Why bad:** debugging geometry in C++ without a visualisation is slow.
Each iteration = recompile + redeploy bundle + restart AC.

**Conclusion:** **iterate geometric algorithms in Python (Shapely +
matplotlib).** C++ only for the final, verified version. The reason for
returning to Python in FloorPlan6.

---

## VERSION CHRONOLOGY — WHY WE BUILD FloorPlan6

```
FloorPlan2 → FloorPlan3 → FloorPlan4 (Python) → FloorPlan4_CPP → FloorPlan6 (Python)
   │             │              │                    │                  │
   │             │              │                    │                  │
heuristics   abandoned     36/36 tests          Stage 3 works     reuse from 4 + lessons from CPP
PyQt5                       OR-Tools             Stage 4 broken    algorithms in Python
                            27 plans w/ graph    Plot Sub buggy    C++ port later
```

**FloorPlan5 = documentation only** ("everything in C++" decision approved
2026-04-26 — reversed 2026-04-29 after the Plot Subdivider session).

**FloorPlan6 = return to Python** in order to:
1. Fix the bathroom 13 m² with a regression test (Stage 4)
2. Design Plot Subdivision with Shapely + matplotlib (Stage 1, future
   session)
3. Have stable logic before starting the C++ port

---

## LESSONS FROM 2026-04-25 (C++ FloorPlan4_CPP)

### What went wrong
- **25+ regression commits** in one area (PolygonFiller)
- **4 failed architectural approaches** to room layout
- **Bathroom 13 m² in a trapezoid** (262 % over the 5 m² limit)
- No plan, no OK, patching instead of rewrite

### What worked (rare)
- Debug log to a text file — helped find the BADPOLY error
- Decoded hex error code (0x81060069 → APIErrorStart+105)

### Conclusion
**FUNDAMENTAL_RULES were written AFTER this session.** They were the result
of analysing what went wrong. **Do not repeat.**

---

## LESSONS FROM 2026-04-29 (C++ FloorPlan4_CPP — Plot Subdivider)

### What was completed (works)
- Palette reorganisation
- BADPOLY fix (APIERR -2130313111) — `coords[nv+1] = coords[1]` + alloc `nv+2`
- BLIZNIACZA fix (`seg_w = min_front_m` instead of `bw/2`)
- Preview legend + building zone

### What went wrong (Plot Subdivider — 4 bugs)
1. Sub-plots overflow the boundary (grid in local AABB, no clipping)
2. Internal roads overflow the plot (stretched across the whole AABB)
3. Building zone ignored (sub-plots in plot outline, not in the building zone)
4. 36 zones inserted for a plot that fits ~10 (greedy algorithm)

### Conclusion
**Geometric algorithm written directly in C++ without a visual prototype =
bugs.** Re-implementation in Python with Shapely (clipping `intersection`)
and matplotlib (visual debugging) — in FloorPlan6, in a separate session
after deciding Q1–Q5 (see `docs/OPEN_QUESTIONS.md`).

---

## LESSONS FROM FloorPlan6 sessions 1–8 (2026-04-30 to 2026-05-05)

### Session 1 (Stage 4 environment + verification F1/F2)
- Found the bathroom 5 m² bug was carried over from C++: solver had no MAX
  cap, validator only checked MIN. Documented as BUG #1.

### Session 2 (BUG #1 fix)
- Added `WT_MAX_AREA = {"lazienka": 5.0, "wc": 3.0}` constant + solver cap +
  validator check. Bathroom can no longer exceed 5 m² physically.

### Session 3 (BUG #2 fix + Q6 distribution)
- After F2 fix, validator started failing for real PL apartments (their
  bathrooms are bigger). Added `strict_max_areas` flag — strict for
  generated, lenient for reference data.
- Q6 implemented in `_compute_target_areas`: living room takes 80 % of
  excess area, bedrooms 20 % proportionally.

### Sessions 4–6 (ArchiCAD bridge, AC integration)
- Verified Tapir Add-On bridge end-to-end: read Zone outline → generate →
  export Zones back to AC.
- Fixed `_detect_notch` for Zone polygons that contain collinear vertices
  (AC sometimes returns redundant midpoint vertices on straight walls).

### Session 7 (Stage 3 first attempt — abandoned)
- Wrote `floor_multistair.py` with multi-stair partitioning (one stairwell
  per "strip"). After 3 patch attempts on geometry, **invoked rule B1**:
  rewrite from scratch with a different approach.

### Session 8 (Stage 3 rewrite — current)
- Deterministic geometry instead of CP-SAT for layout positions.
  `core/floor_layout.py` from scratch. Covers 200 m², 800 m² and 1200 m²
  rectangular floors with status OK and walking distance ≤ 40 m WT.
- L-shape / U-shape support remains TODO (open to contributors).

---

## SUMMARY ONE-LINER

**5 patterns to reuse (Coverage==, scale=100, topology blocking, notch
detection, trapezoid handler) + 6 mistakes to avoid (absorb, MIN_SHARED 90cm,
Coverage<=, patching, hub spine, C++ without Python prototype). All
documented in sessions 25-04 and 29-04, plus the FloorPlan6 session log
above.**
