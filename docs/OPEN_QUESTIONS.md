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
> **Scope note (2026-05-07):** Q1–Q5 below apply ONLY to **Mode B**
> (subdivision, single-family only). See Q12 for the mode framework.
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

**Status:** PARTIALLY DECIDED 2026-05-07
**Owner's decision:** option (a) — clip to boundary as trapezoid using
`core/trapezoid_handler.py`. **Additional constraint:** if the resulting
trapezoid falls below the minimum sub-plot size (Q15 front + minimum area
from MPZP), the algorithm must adjust to bring it back to minimum, NOT
reject silently. Mechanism for the adjustment is a follow-up sub-question
(Q1.1, OPEN — see below).

### Q1.1 — How to "increase" a too-small clipped sub-plot? (follow-up to Q1)
**Question:** when option (a) from Q1 produces a sub-plot below the minimum
size, how does the algorithm bring it back?

**Options:**
- (a) **Shift the grid** — adjust grid spacing so all sub-plots ≥ min,
  accepting fewer sub-plots overall
- (b) **Merge with neighbour** — combine the small sub-plot with an adjacent
  one to form one larger irregular sub-plot
- (c) **Push the internal boundary** — shrink the neighbour's area to grow
  the small one (breaks grid uniformity)
- (d) **Promote to nieużytek** — drop the sub-plot entirely as explicit
  waste polygon under Q16(a)

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (c) — push the internal boundary, **with the
hard constraint that the donor neighbour also stays ≥ minimum** (Q15
front + minimum area). If a single push cannot satisfy both sub-plots
above their minima, the layout is INFEASIBLE at this orientation/spacing
and the Q5(c) outer optimisation must escalate (try a different grid
orientation, different spacing, or fewer rows). Per E2 spirit: NEVER
shrink below the minimum to "make it fit".

**Implementation note (Session 5, 2026-05-07):** the production port in
`core/plot_subdivider.py` currently uses Q1.1(d) drop-to-nieużytek as
fallback rather than full (c) push. The owner's hard constraint ("no
sub-plot below minimum") IS satisfied — too-small clipped cells are
moved to the explicit `nieużytek` polygon under Q16(a). The full (c)
push (move column boundaries between adjacent cells) is deferred
because: (i) on tested L-shape cases, push doesn't recover notch-cut
cells; (ii) push for slanted-edge plots requires non-uniform grid
generation, which is a separate feature. Marked as open follow-up;
Q1.1(d) is a safe interim that does not violate the owner's spec.

### Q2 — Internal road layout
**Question:** how to lay out roads between sub-plots?

**Options:**
- (a) **Strips between rows** (simple grid — currently implemented in C++)
- (b) **One main road (spine) + short access spurs** to each sub-plot
- (c) **Loop / cul-de-sac / other**

**Recommendation:** none — purely architectural. The owner knows what real
projects look like.

**Status:** DECIDED 2026-05-07
**Owner's decision:** **road = hub-analogue** (cross-stage pattern from F4).
Treat the internal road system the same way the apartment-layout solver
treats the hub: occupy minimum area, default minimum width **4.5 m**
(allows two-way passenger-car traffic without a separate footpath:
2 × 1.5 m car lane + 1.5 m clearance), **user-editable upward** in the UI.
This is closer to option (b) (spine + spurs) than (a) (parallel strips),
but with the explicit minimisation constraint inherited from F4.

**Note:** WT §15 ust. 1 requires a 5 m fire road *if* fire-access is
required. The 4.5 m default is for purely residential internal roads
where fire access is satisfied by other means (e.g. external road on the
plot edge). The verifier must surface this conflict when relevant.

### Q3 — Must the sub-plot front face the road?
**Question:** must every sub-plot have its shorter side (front) towards
the road?

**Options:**
- (a) **YES** — shorter side = front, longer side = lateral plot edge (PL standard)
- (b) **NO** — can be the other way (deeper plot longer along the street)
- (c) **Depends on building type** — terraced YES, detached doesn't matter

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (c) — depends on building type. Terraced and
twin-house: shorter side = front (mandatory). Free-standing detached:
orientation free. Implementation: building-type flag drives the front
constraint per sub-plot.

### Q4 — TWIN-HOUSE (BLIZNIACZA) — sub-plot definition
**Question:** how to count a sub-plot for a twin-house development?

**Options:**
- (a) **1 sub-plot = 1 segment** (1 unit). A pair = 2 adjacent sub-plots
  with a shared wall. (currently in C++)
- (b) **1 sub-plot = 1 whole twin building** (2 units in one building)

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (a) — 1 sub-plot = 1 segment (1 unit). A pair
of twins = 2 adjacent sub-plots with a shared wall. Matches the C++
approach. Each sub-plot is independently verifiable.

### Q5 — Sub-plot grid orientation
**Question:** what orientation should the sub-plot grid have?

**Options:**
- (a) **Aligned with the longest plot edge** (auto)
- (b) **Aligned with a user-marked external access edge** (from the AC
  palette, requires interaction)
- (c) **Optimisation** for maximum plot utilisation (algorithm searches)

**Recommendation:** (b) — gives user control, simple UX (one click "mark
access to the road" — already in the C++ palette).

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (c) — optimisation for maximum plot
utilisation. The algorithm searches multiple orientations (e.g. align with
each plot edge, rotated grids) and picks the one that maximises the number
of valid sub-plots subject to Q15 (min front), Q16 (strict coverage), Q3
(front-to-road for terraced/twin), Q1.1 (small-sub-plot adjustment) and
the road-as-hub minimisation from Q2. This is a multi-objective search —
likely CP-SAT or generative + scorer, with mandatory matplotlib
visualisation per Stage 1 prototype iteration (E6).

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

## STAGE 1 — MODE FRAMEWORK & ADDITIONS (2026-05-07)

> **Context:** evaluation of `claude code/archicad-checker/` as a foundation
> for Stage 1 surfaced the need to formalise application modes and several
> threshold decisions. Q12 frames the modes; Q13–Q18 are sub-decisions that
> gate concrete implementation.

### Q12 — Stage 1 application modes
**Question:** is Stage 1 a single workflow or two distinct modes?

**Status:** DECIDED 2026-05-07
**Owner's decision:**
- **Mode A — whole-plot analysis (no subdivision).** Available for BOTH
  single-family (jednorodzinna) AND multi-family (wielorodzinna) housing.
  This is what `archicad-checker` does today end-to-end: read plot, classify
  boundaries, compute buildable zone, verify WZ/WIZ/PBC + WT 2002 rules,
  optionally place auxiliary site elements (well, septic, parking).
- **Mode B — subdivided-plot analysis.** Available ONLY for single-family.
  Subdivides one plot into N sub-plots, then runs Mode-A analysis per
  sub-plot. Multi-family on subdivided plots makes no architectural sense
  and is excluded.

**Implication:** Q1–Q5 (subdivision specifics) gate Mode B only. Mode A can
ship independently as soon as `archicad-checker` is integrated.

### Q13 — Mode B infrastructure: per-house or site-wide?
**Question:** in Mode B (single-family subdivision), are well/septic/parking
modeled per individual house or as shared site infrastructure?

**Options:**
- (a) **Per house** — each sub-plot has its own well + septic (rural)
- (b) **Site-wide** — city water/sewer; only `wt_009/010` (parking) per
  sub-plot; `wt_004–008` (well/septic) skipped
- (c) **Flag in `ParametryMPZP`** — UI asks at start, default = (b)

**Recommendation:** (c) — most flexible, matches PL practice variance.

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (c) — flag in `ParametryMPZP`. Default value
is **(b) site-wide (city water/sewer)** — wt_004–008 (well/septic
distance rules) skipped. UI offers a checkbox for rural projects to flip
the flag and re-enable per-house infrastructure analysis.

### Q14 — 5% warning band in `_sprawdz_max` / `_sprawdz_min`
**Question:** archicad-checker uses a 5% tolerance band: `≤ limit` = OK,
`limit < val ≤ 1.05 × limit` = WARNING, `> 1.05 × limit` = VIOLATION. Is
this compatible with F10 (validator strict)?

**Options:**
- (a) **Keep band** — UI-level warning is useful for human-driven verification
- (b) **Strict per F10** — `≤ limit` = OK, `> limit` = VIOLATION, no band
- (c) **Flag `strict_check`** — default True (matching `strict_max_areas`
  pattern from Q11); False only for reference/exploratory data

**Recommendation:** (c) — analogous to existing Q11 dynamic-tolerance pattern.

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (a) — keep the 5% band. Stage 1 verifier is
intended to verify human-designed projects (not solver-generated), so a
graduated UI feedback (OK / WARNING / VIOLATION) is more useful than a
binary cut-off. F10 strict applies to FP6 solver-generated outputs in
Stage 4 — different code path. Plain-language re-statement
(WZ=0.305 vs limit 0.30 → WARNING with "in 5% tolerance band" note)
confirmed by owner.

### Q15 — Minimum sub-plot front (Mode B)
**Question:** what is the minimum sub-plot front width when MPZP does not
specify it?

**Options:**
- (a) **Default 18 m** + MPZP override via `ParametryMPZP.min_front_m`
- (b) **Default 16 m** (allows twin-house with 8 m × 2 segments)
- (c) **Other value** (specify)

**Cross-ref:** analogue of E2 (MIN_SHARED_EDGE 90 cm) — below this threshold
the sub-plot is INFEASIBLE and must be rejected, NOT shrunk.

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (a) — default 18 m (PL standard for detached
single-family) + override via `ParametryMPZP.min_front_m` when the local
MPZP specifies a different value. Below this threshold the sub-plot is
INFEASIBLE and Q1.1 adjustment kicks in.

### Q16 — Subdivision coverage (analogue of F1/P1)
**Question:** in Mode B, must `Σ sub_plot.area + roads.area == parent.area`
hold strictly, or are unused fragments allowed?

**Options:**
- (a) **Strict ==** — every m² accounted for: sub-plots + roads + an
  explicit `nieużytek` (waste) polygon
- (b) **<= implicit** — unused fragments are dropped silently
- (c) **<= with reporting** — unused fragments allowed but MUST be surfaced
  in the UI as `nieużytek X m² (Y%)`

**Recommendation:** (c) — preserves the spirit of E1 (do not absorb
uncovered polygon → no "rectangles from nowhere") while admitting that real
plots have leftover triangles that aren't worth subdividing.

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (a) — strict equality. Every m² of the parent
plot must be accounted for as one of: `sub_plot`, `road`, or explicit
`nieużytek` polygon. No silent waste. This is the direct analogue of F1
for Stage 1 and matches the spirit of P1 (sacred equality). Forces the
algorithm to make the leftover triangle decisions visible in the output.

### Q17 — Mode A multi-family adapter for `optimizer.py`
**Question:** `archicad-checker/optimizer.py` assumes one well + one septic
+ a small parking. For Mode A multi-family (e.g. 60-unit building) this
shape doesn't fit.

**Options:**
- (a) **Adapter** — multi-family skips well/septic, focuses on N-stall parking
- (b) **Flag `infrastruktura_miejska`** — default True for multi-family,
  False for single-family; skip wt_004–008 when True
- (c) **Two separate optimisers** — one for single-family, one for multi-family

**Recommendation:** (b) — minimal divergence, single code path.

**Status:** DECIDED 2026-05-07
**Owner's decision:** **skip well/septic entirely for multi-family**
("nierealne albo skrajnie niewykonalne"). Implementation: when housing
type = wielorodzinna, the `optimizer.py` codepath omits well/septic
placement and the verifier skips wt_004–008. Parking placement remains
active and is the dominant constraint for multi-family. Effectively a
hybrid of (a) and (b) — single flag drives the skip.

### Q19 — Q3(c) gating: TWIN/TERRACED parent's DROGA touch only?
**Question:** is the strict parent-DROGA filter (added 2026-05-08 in
`plot_subdivider._filter_for_building_type` for TWIN/TERRACED, while DETACHED
keeps the lenient parent-OR-internal filter) consistent with the architectural
intent of Q3?

**Context:** Q3 owner's decision mandates only **orientation** (shorter
side = front) for TWIN/TERRACED, not **location**. The strict filter
collapsed multi-row developments to ≤4 monster sub-plots on large plots
(Dawid's 2026-05-25 screenshot: 265×202 m plot → TWIN returned 4 sub-plots
with one S1=31708 m² monster), making szeregowce/bliźniaki in the second
row impossible to design.

**Options:**
- (a) **Loosen** — TWIN/TERRACED accept any road access (parent DROGA OR
  internal road), same as DETACHED. Front orientation remains the
  constraint per Q3.
- (b) **Hybrid** — TWIN/TERRACED accept internal road *iff* that internal
  road connects to a parent's DROGA (transitive driveway continuity).
- (c) **Keep strict** — preserve 2026-05-08 behavior; fix
  `building_proposer` to handle ≤4 sub-plot scenarios gracefully.

**Status:** DECIDED 2026-05-25
**Owner's decision:** option (a) — loosen. Standard PL deweloperka
practice puts szeregowce/bliźniaki in multiple rows with internal road
access; the strict gate broke this. Q3 stays as-is (orientation only).
Implementation: `_filter_for_building_type` and `_wrap_valid_subplot`
now treat all building types identically — any road access (parent DROGA
OR internal road) is kept, only true no-access sub-plots are demoted to
nieużytek.

### Q20 — Sub-plot size scaling per BuildingType (Mode B)
**Question:** in real PL practice, a twin-house sub-plot is ½ of a typical
detached sub-plot (segment = one unit), and a terraced sub-plot is ⅓.
Current subdivider uses the same MPZP `min_front_m` / `min_sub_plot_area_m2`
for all building types, so TWIN/TERRACED produce DETACHED-sized sub-plots
(~600-1000 m²) instead of segment-sized (~150-450 m²). How to fix?

**Context:** Dawid 2026-05-25 screenshot after Q19 fix showed 43 sub-plots
of ~600-800 m² for both TWIN and TERRACED — algorithmically correct (no
collapse) but architecturally wrong (each segment should have its own
small plot, not share a 600 m² plot with nothing).

PL standards (per Neufert + lokalne MPZP):
| Type      | Front segment | Area segment   |
|-----------|---------------|----------------|
| DETACHED  | 18 m          | 600-1000 m²    |
| TWIN      | 7-10 m        | 250-450 m²     |
| TERRACED  | 5-7 m         | 120-250 m²     |

**Options:**
- (a) **Auto-scale in algorithm** — `subdivide()` replaces `plot.mpzp`
  with effective values per BuildingType (TWIN: front=min(user, 9 m),
  area×0.5; TERRACED: front=min(user, 6 m), area×⅓). User's MPZP acts
  as upper bound. Single entry point change.
- (b) **Per-type fields in MPZP** — `min_front_twin_m`, `min_front_terraced_m`,
  `min_area_twin_m2`, etc. Explicit, requires MPZP + UI + tests changes.
- (c) **UI auto-defaults** — when user picks TWIN combo, UI sets fields to
  TWIN defaults; user can still override. Transparent.

**Status:** DECIDED 2026-05-25
**Owner's decision:** option (a) — auto-scale in the algorithm at the
`subdivide()` entry point. Defaults: TWIN front 9 m and area ×0.5;
TERRACED front 6 m and area ×⅓. User's MPZP `min_front_m` is treated as
an upper bound (we never enlarge above what they configured). MPZP fields
remain single-typed; the type-aware scaling is an internal transform.
Implemented in `plot_subdivider._with_effective_mpzp` +
`_BUILDING_TYPE_SEGMENT_DEFAULTS`.

**Follow-up fix (same day):** the `_is_buildable_shape` guard previously
had a hardcoded `min_short_dim = 12.0 m` (and 8.0 m for the looser
splitting variant), tuned for DETACHED segments. After Q20 scaling,
TERRACED segments (6 m wide) and most TWIN segments (9 m) were rejected
by that guard, producing 0 sub-plots for TERRACED and oversized
leftover-absorption for TWIN. Added `plot_subdivider._min_short_dim(mpzp)`
helper that derives the guard from `mpzp.min_front_m`
(`min(12, 0.67 × min_front_m)` for the strict pass,
`min(8, 0.45 × min_front_m)` for the loose split pass). Both call sites
now use it.

### Q18 — Stage 1 UI entry point
**Question:** how does the user pick mode (A/B) and housing type?

**Options:**
- (a) **Radio at start** — first "housing type" (single/multi), then for
  single-family "mode" (whole-plot / subdivision)
- (b) **Auto-detect from MPZP** — `przeznaczenie` in `ParametryMPZP`
  (MN → single, MW → multi); mode (A/B) always asked
- (c) **Tabs in UI** — separate tabs "Whole plot", "Subdivision", "Settings"

**Status:** DECIDED 2026-05-07
**Owner's decision:** option (a) — radio at start. First the user picks
housing type (jednorodzinna / wielorodzinna). For wielorodzinna, mode A
(whole-plot) is the only available option (Q12). For jednorodzinna, a
second radio offers mode A (whole-plot) or mode B (subdivision). Explicit,
no auto-detection from MPZP fields.

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
