# Stage-4 House: open-plan day-zone + scaled program + single-storey + realistic furniture

**Date:** 2026-06-02 · **Status:** approved (Dawid, "widzę że założenia są słuszne — ruszaj")
**Sessions:** 19+ · **Branch:** `feat/sfh-open-plan-day-zone`

## Why

Session 18 shipped a credible staircase (Approach B). Dawid then asked to (a) ground the room layout
**and** furniture in his real PROJ-BUD/Łącko plans, not hand-waved "ARCHON", supplemented by Neufert
*Architects' Data*; and (b) make the generator handle his calibration footprints **35 / 70 / 120 m²**
(5×7 / 10×7 / 10×12). Vision-analysis of all 49 reference plans + a Neufert research pass produced a
grounded ruleset (below). The headline finding: the **day zone is open-plan** (kitchen+dining+living =
one continuous space, often **L-shaped**), which our separate-walled `salon`+`kuchnia` template does
not model. Layout + inter-room dependencies are the foundation; furniture sits on top.

## Grounding (what the plans + Neufert actually say)

**Confirmed by Dawid's plans (strong, recurring):**
- Stair + compact hub = **central core, mid-depth, internal wall, never a facade** (confirms Approach
  A/B). U/winder on near-square footprints, straight run on narrow/long ones.
- **Open-plan day zone** dominant: salon+kuchnia+jadalnia = one space, **combined area cap**
  (~0.30–0.36·usable), pinned to the **garden facade** (most glazing, opposite the entry). Entry/garage/
  technical face the street. Separate walled kitchen only in cheap/traditional/small plans.
- **Kitchen L-counter** wrapping a corner on two walls; **sink under a window** (near-universal, treat
  as hard); hob on a different leg; fridge ends the run; backs the central plumbing core.
- **Bed headboard flush to a solid interior wall**, never under a window; nightstands flank; window at
  side/foot. (Correction to an earlier wrong assumption: it is **storage/wardrobe/bathtub** that goes
  under the attic slope, **not the bed** — bed body stays in the full-height zone.)
- **Sofa (often L/corner) backs an interior wall**, faces the TV wall + garden glazing; coffee table
  centred; armchairs form a U. Window/terrace wall kept clear of furniture.
- **Bathroom internal** (windowless interior band ok), fixtures lined on one/two **wet walls**, WC in a
  corner set back from the door, **door swings outward** (F8); wet rooms **stack vertically** over one
  plumbing core by the stairs (cross-floor).
- **Vertical zoning:** parter = day zone + garage/technical (+ optional 1 ground bedroom); poddasze =
  night zone (3–4 bedrooms + family bath + garderoba + landing). Master = largest, often suite.
- **Scale tiers:** ~35 single-storey studio (no stairs); ~58–70 compact; ~95–120 mid+garage; ~150+
  large. Room count scales with size.

**Neufert (clearances, metres) — geometry from the plans, gaps from Neufert:**
- Walkway ≥0.80 (0.75 hard min); door clear zone 0.80×0.80; wall inset 0.10.
- Bed: double 1.4×2.0 (master 1.6×2.0); access side ≥0.70, foot ≥0.70; hinged wardrobe front ≥0.90
  (sliding ≥0.75); nightstand 0.50×0.40.
- Living: sofa 3-seat 2.2×0.9 (2-seat 1.5×0.9); TV unit 1.5×0.4 opposite; coffee table 1.1×0.55,
  sofa-front→table ≥0.40, table→TV walk ≥0.75, viewing ≥1.80; needs ~3.0–3.5 m sofa-wall→TV-wall.
- Dining (centred, NOT wall-hugging): table 4-seat 1.2–1.4×0.85, 6-seat 1.6–1.8×0.85; seated side
  ≥0.80, door-facing edge ≥1.20; place between kitchen and salon.
- Kitchen: counter depth 0.60; work aisle ≥1.20 (1.50 target); sink under window with ≥0.80 prep
  beside; hob ≥0.30 each side, off corner; fridge 0.60 box ending a leg with ≥0.40 landing; snap 0.10.
- Bathroom: tub 1.7×0.7 (front 0.90×0.75); shower 0.9×0.9; basin 0.6×0.5 front ≥0.55; WC 0.4×0.65
  front ≥0.60, ≥0.20 each side. Parter compact (≤5), attic family/master 6–12.

## Decomposition (sequenced, Dawid chose 1→2→3→4)

Each sub-project: spec section → TDD → render → verify. M1–M5 apartment path stays byte-identical
(every house behaviour gated on `program_config`).

1. **Open-plan day zone (foundation, on 70).** ✅ DONE (branch `feat/sfh-open-plan-day-zone`):
   combined DZIENNA cap (`house_program.day_zone_cap`, pct 0.60/max 45, soft anti-bloat ceiling);
   salon lands on the garden facade (verified robust 9/9, no forcing needed); day-zone contiguous →
   forms an L; renderer draws DZIENNA rooms with no internal wall (one open L-space). Tests
   `tests/test_open_plan_dayzone.py` + `test_day_zone_combined_cap`.
   **2a — minimal corridor (Dawid's feedback) ✅ DONE:** re-enforced hub-minimal (F4) for houses;
   F1 overflow now routes to BEDROOMS (poddasze) / day-zone (parter), NOT the hub (reverses session-18
   overflow→hub). Result on 9×7: podest 15.6→6.3, bedrooms grew to 12–15.5. Bloat test reframed to
   `test_corridor_minimal_excess_to_bedrooms`. Full house+apartment regression **70 passed / 1 xfailed**.
2. **2b — scoped NATIVE L-rooms (Dawid chose native over post-process) + 2c scaled set.**
   **L-capable rooms = hol/corridor (both storeys) + bedrooms (poddasze, exceptional).** Each L-capable
   room may be a union of 2 rectangles (L) or stay rectangular; the solver picks L only when it
   MINIMIZES the corridor. Mechanism: an OPTIONAL second rectangle per L-capable room (CP-SAT
   `new_optional_interval_var` with presence literal `has_L[i]`); NoOverlap2D over primary+optional
   rects; coverage sums present areas; adjacency = either rect touches; the 2 rects of one room must be
   contiguous (share an edge) → L. **Motivates the fix** for the WC-landlocked + wiatrołap-not-at-door
   bugs: forcing those placements on the rectangular model bloated the hol 7→11 (>F4); an L-hol wraps
   them while keeping its AREA minimal. RISK: substantial CP-SAT change, feasibility-delicate (session-18
   lesson) — TDD carefully, RED feasibility tests first across the footprint/entry matrix. Renderer
   already handles `MultiPolygon`; furniture needs L-aware placement (largest inscribed rect / per-arm).
   Scaled set (2c): big footprints add gabinet → 4th bedroom → garage so the capped set fills usable
   instead of ballooning one room (probe: 10×12 day-zone 83, bedrooms 27–38 — clearly needs this).
   **Deferred bugs (fix WITH 2b L-rooms):** WC must touch an external wall; wiatrołap must be the airlock
   at the entry door (small, hol behind) — both regressed the corridor on the rectangular model.
3. **Single-storey mode (for 35).** No stairs/wiatrolap/separate kitchen; lower `MIN_STOREY_AREA`.
4. **Realistic furniture (all tiers).** Sub-zone the day zone + bedrooms + bathroom; window-aware.

**Test footprints (added per Dawid):** 5×7=35 (single-storey, phase 3), 10×7=70 (phase 1 primary),
10×12=120 (phase 2). Until their phase lands: 35 → clear `ok=False` "too small for 2-storey"; 120 →
generates feasibly but shows the overflow GAP (documented).

---

## Phase 1 — Open-plan day zone (Approach B)

**Model (Dawid's B, not a single rectangle):** the day zone is a **group of functional sub-rectangles**
(`salon` + `kuchnia`, optional `jadalnia`) that are:
- separate room **ids** (so furniture knows kitchen vs living),
- **un-walled** (rendered as one open space — no internal wall line between group members),
- **contiguous** (share an edge via the existing `salon↔kuchnia` opening) → free to form an **L** or a
  rectangle (we do NOT force a rectangle),
- share **one combined cap** (~0.30–0.36·usable) so excess doesn't bloat one sub-room.

**Changes:**
1. **Templates** `house_parter.json`: keep `salon` (DZIENNA, priorytet 1) + `kuchnia` (DZIENNA,
   priorytet 2) as separate ids; tag them an open-plan group (`open_plan_group: "day_zone"` field, or
   derive from `strefa==DZIENNA`). Keep `salon↔kuchnia` opening (contiguity); `spizarnia↔kuchnia`.
2. **`house_program.py`:** cap the **SUM** of the DZIENNA group at a combined cap (`day_zone` cap, e.g.
   `min(0.36·usable, ~45)`, floor ~22), instead of independent salon 35 + kuchnia 13. Overflow fills the
   group up to the combined cap, then the hub (existing sink logic, now group-aware).
3. **Solver:** pin `salon` (day-zone anchor) to the **garden facade = the wall opposite the entry**
   (most glazing). Reuse `forced_facade` or add an entry-opposite facade constraint. Keep group
   contiguity via adjacency.
4. **Renderer:** suppress the wall line on edges shared between two DZIENNA-group rooms (open-plan look);
   optional faint zone hint.
5. **M1–M5 untouched** (combined-cap + garden-facade gated on `program_config is not None`).

**Tests (TDD, RED first):**
- combined DZIENNA cap: on a large footprint, `salon.area + kuchnia.area ≤ combined_cap` (not 48).
- salon touches the entry-opposite (garden) facade.
- day-zone group contiguous (salon shares ≥0.9 m edge with kuchnia).
- M1–M5: `test_reserved_core_none_is_unchanged` + apartment e2e unchanged.
- feasibility on **10×7 (70)** + the session-18 entry/footprint matrix still green.
- render smoke: no internal wall between salon & kuchnia.

**Verify:** full non-GUI suite green; render `notebooks/output` 10×7 shows one open L/rect day zone on
the garden facade, hub central, stairs (Approach B) intact.

---

## Phase 2 — Minimal corridor + overflow→bedrooms + L-shaped rooms + scaled set — outline

**Dawid's feedback on the phase-1 render (2026-06-02, [[feedback_corridor_minimal_lshaped_rooms]]):**
the poddasze podest was 15.6 m² ≈ 22% of the floor — **the corridor must be MINIMAL (F4)**; excess goes
to **bedrooms**, which **may be L-shaped polygons**. This REVERSES session-18's overflow→hub + disabled
F4-penalty (which I introduced to keep bedrooms ≤ cap — wrong trade-off; corridor-minimal wins).

- **2a — minimal hub + overflow→bedrooms:** re-enforce the hub-minimal penalty (F4) for houses; route
  the F1 leftover to BEDROOMS (NOCNA) on the poddasze (day-zone on the parter) instead of the hub.
  Bedrooms grow (rectangular). **Relax the session-17 "no bedroom bloat" test** — bedroom growth is now
  the GOAL, and the cap is a soft guide; corridor-minimal is the hard rule. Quick, big visible win.
- **2b — L-shaped bedrooms:** post-process — when a minimal hub leaves a non-rectangular pocket, MERGE it
  into an adjacent bedroom (union → L-polygon), shrinking the hub to its circulation minimum. The
  renderer already handles `MultiPolygon` rooms; **furniture needs L-aware placement** (place in the
  largest inscribed rectangle / per-arm). Dawid explicitly allows L-rooms to optimize space.
- **2c — scaled room-set (for 120):** big footprints add rooms by tier (room_set_by_size from
  [[project_archon_house_adjacency]]): gabinet → 4th sypialnia → garage → larger day zone, so 10×12=120
  fills with 4–5 bedrooms/gabinet, not one huge room.

## Phase 3 — Single-storey mode (for 35) — outline
New `house_single_storey` template: open day zone (living+kitchenette) + 1–2 sypialnie + 1 bath + tiny
hol; **no stairs, no wiatrolap, no separate kitchen**. Lower `MIN_STOREY_AREA` to ~32. `generate_house`
(or a sibling) picks single-storey by area/toggle. 5×7=35 generates a real 1-storey house.

## Phase 4 — Realistic furniture (all tiers) — outline
`place_furniture(rooms, boundary=None)`: derive per-wall **exterior/interior** (window) flags from the
boundary; per-room semantic placers (bedroom / day-zone kitchen+dining+living / bathroom) with the
Neufert clearances above; generic greedy fallback for utility rooms. Dining = centred at the L junction
between kitchen and living. Window=None → degrade to wall heuristics (keeps current tests green).

---

## Decisions
- **Approach B** (functional sub-rects, can form L, combined cap) over A (single rectangle) — Dawid.
- Sequence **1→2→3→4** — Dawid.
- Open-plan is the **default**; a "separate kitchen" toggle is deferred (not v1).

## Deferred (recorded, not in scope now)
Non-rectangular footprints **L/U/trapezoid** (Dawid: "kształty osobno potem"); garage strategy; terrace/
exterior; accessibility mode; fireplace (kominek).

## Open — needs Dawid before touching
- **F2 bathroom cap** (FUNDAMENTAL): plans show attic/master baths 6–12 m². Proposed storey cap parter
  ≤5 / poddasze family ~8 / large-house master ~12. Touches F2 — explicit sign-off required (phase 4,
  when we touch the poddasze bath).
