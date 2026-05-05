# OPEN_QUESTIONS — architectural decisions awaiting answers

> **Rule:** before implementing anything related to the questions below,
> Claude MUST ask the project owner and wait for a decision. Do NOT guess.
> Rule B5.

> **Format:** every question has context (where it came from), options
> (a/b/c), a default recommendation (if there is a sensible one), and a
> status (OPEN / DECIDED).

---

## STAGE 1 — PLOT SUBDIVISION (from C++ FloorPlan4_CPP session 2026-04-29)

> **Stage status:** ⏸️ ON HOLD in FloorPlan6 until a separate session.
> Stage 4 (apartment layout) first.
>
> **Context:** in C++ Plot Subdivider had 4 known bugs (sub-plots overflow
> boundary, roads overflow, building zone ignored, 36 zones for ~10 possible).
> Re-implementation in Python with Shapely + matplotlib. These decisions are
> required BEFORE implementation.

### Q1 — Sub-plots near an irregular boundary
**Question:** what to do with a sub-plot that would partially fall outside
the main plot boundary (or outside the building zone)?

**Options:**
- (a) **Clip to the boundary** → sub-plot has a trapezoid shape (analogy
  with trapezoidal apartments from FloorPlan2/4 — `core/trapezoid_handler.py`
  already exists)
- (b) **Reject entirely** → only full rectangles
- (c) **Shrink** → smaller rectangle that fits inside

**Recommendation:** (a) — trapezoid handler infrastructure already exists.
But it's the project owner's call.

**Status:** OPEN

### Q2 — Internal road layout
**Question:** how to lay out roads between sub-plots?

**Options:**
- (a) **Strips between rows** (simple grid — currently implemented in C++)
- (b) **One main road (spine) + short access spurs** to each sub-plot
- (c) **Loop / cul-de-sac / other**

**Recommendation:** none — purely architectural. The owner knows what real
projects look like.

**Status:** OPEN

### Q3 — Must the sub-plot front face the road?
**Question:** must every sub-plot have its shorter side (front) towards
the road?

**Options:**
- (a) **YES** — shorter side = front, longer side = lateral plot edge (PL standard)
- (b) **NO** — can be the other way (deeper plot longer along the street)
- (c) **Depends on building type** — terraced YES, detached doesn't matter

**Status:** OPEN

### Q4 — TWIN-HOUSE (BLIZNIACZA) — sub-plot definition
**Question:** how to count a sub-plot for a twin-house development?

**Options:**
- (a) **1 sub-plot = 1 segment** (1 unit). A pair = 2 adjacent sub-plots
  with a shared wall. (currently in C++)
- (b) **1 sub-plot = 1 whole twin building** (2 units in one building)

**Status:** OPEN

### Q5 — Sub-plot grid orientation
**Question:** what orientation should the sub-plot grid have?

**Options:**
- (a) **Aligned with the longest plot edge** (auto)
- (b) **Aligned with a user-marked external access edge** (from the AC
  palette, requires interaction)
- (c) **Optimisation** for maximum plot utilisation (algorithm searches)

**Recommendation:** (b) — gives user control, simple UX (one click "mark
access to the road" — already in the C++ palette).

**Status:** OPEN

---

## STAGE 4 — APARTMENT LAYOUTS (NEW Q's appear here after the first session)

### Q6 — Bathroom — who absorbs the "extra area"?
**Question:** if the apartment polygon has more area than the sum of room
`min_powierzchnia` (typical case), who absorbs the excess so F1
(100 % coverage) is satisfied?

**Options:**
- (a) **Living room (`salon_aneks`)** — has the widest `procent_powierzchni`
  range (max 45 %)
- (b) **Master bedroom** — second largest
- (c) **Hub** — but this breaks F4 (hub max 15 %)

**Status:** DECIDED 2026-04-30
**Owner's decision:** living room takes **80 % of the excess**, the remaining
**20 % is distributed proportionally among the bedrooms**. Bedrooms do NOT
have to sit at the minimum — they can go above. Hub and service rooms
(bathroom, WC) stay at `procent_powierzchni` or the WT hard cap (Q7).

Example: 100 m² apartment, sum of `min_powierzchnia` = 60 m² → excess 40 m²
→ living room +32 m², bedrooms together +8 m² (proportional to their
respective `min_powierzchnia`).

### Q7 — 5 m² bathroom vs `procent_powierzchni`
**Question:** in `M3_standard.json` the bathroom has
`procent_powierzchni: [0.06, 0.12]`. For a 100 m² apartment that's 6–12 m².
Conflict with F2 (max 5 m²).

**Options:**
- (a) **F2 wins** — `min(procent_powierzchni × usable, 5.0)` as a hard cap
- (b) **Procent_powierzchni wins** — but this breaks F2

**Status:** DECIDED 2026-04-30
**Owner's decision:** option (a) — **F2 wins**. WT hard cap takes precedence
over template `procent_powierzchni`.

**Refined caps (2026-04-30):**
- Bathroom: min 2.5 m² / opt ~4.5–5.0 m² / **max 5.0 m²**
- WC: min 1.5 m² / **opt 1.8 m²** / **max 3.0 m²**

Effective upper bound: `min(procent_max × usable_area, WT_MAX_AREA[room_id])`.
Implementation: `WT_MAX_AREA` constant in `config.py` +
`model.add(area_i <= max_area_cm2)` in solver + `_check_max_areas` function
in validator.

### Q8 — Staircase in Stage 4
**Question:** does Stage 4 receive only the apartment outline (already
without the staircase) or the outline including the staircase to be cut out?

**Options:**
- (a) **Without staircase** — Stage 3 (Floor mode) already cut the staircase
  out, Stage 4 receives clean apartments
- (b) **With staircase** — Stage 4 cuts it out itself

**Recommendation:** (a) — separation of concerns.

**Status:** OPEN

---

## STAGE 3 — FLOOR (when porting from C++)

### Q9 — How to port Floor mode from C++ to Python
**Question:** Floor mode (Stage 3) works in C++ (6/6 tests). Should the
Python port be 1:1 or a re-implementation?

**Options:**
- (a) **1:1 port** — faster but C++ idioms in Python
- (b) **Re-implementation** — slower but clean Pythonic code (Shapely
  instead of manual geometry)

**Recommendation:** (b) — Stage 4 is also Pythonic, so unified style.

**Status:** PARTIALLY DECIDED — for FloorPlan6 we wrote Stage 3 in Python
from scratch (`core/floor_layout.py`). The C++ Floor mode remains a
reference for any feature we might miss.

---

## CROSS-CUTTING

### Q10 — Python Palette in AC vs CLI
**Question:** how does the end-user run FloorPlan6?

**Options:**
- (a) **Python Palette in AC** (wrapper around Tapir) — clicks a button in AC
- (b) **CLI** — `python main.py` from a terminal
- (c) **PyQt5 GUI** (`ui/main_window.py`) — desktop window

**Recommendation:** ultimately **(a)** for architects. **(b)+(c)** for
developers. Verify how Tapir Python Palette is configured.

**Status:** OPEN — decision before the first deployment to a user.

### Q11 — Validator API: `strict_max_areas` flag
**Question:** validator was failing for reference Polish apartments after
F2 was added (real apartments sometimes have 6–8 m² bathrooms, exceeding
the WT cap). How to handle this?

**Options:**
- (a) `_check_max_areas` reports WARNING instead of ERROR
- (b) **Flag `validate(fp, strict_max_areas: bool = True)`** — default True
  (strict for generated plans), False for reference data
- (c) Heuristic by `template.source` — skip MAX check if `source != "manual"`
- (d) Lower the test threshold

**Status:** DECIDED 2026-04-30
**Owner's decision:** option (b) — flag `strict_max_areas`. Default True —
strict for plans generated by the solver. False for reference plans from
`data/plans/` (real PL apartments may have bathrooms > 5 m²). Consistent
with the existing dynamic-tolerance pattern in `_check_area_coverage`.

---

## DECIDED (example — once we move an answer here)

> Format after a decision:
> ```
> ### QX: [question]
> **Status:** DECIDED YYYY-MM-DD
> **Decision:** option (a) — owner's reasoning: ...
> ```

---

## PROCESS

1. Claude hits a decision → checks this file
2. If Q is OPEN → STOP, asks the owner
3. After the owner's decision → Claude UPDATES this file (moves Q to
   DECIDED with date and reasoning)
4. Claude implements according to the decision
5. If implementation reveals new questions → ADD as Q11, Q12, …

**Rule B5:** ask about architectural decisions, NOT obvious things.
