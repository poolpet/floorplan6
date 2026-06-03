# Stage-4 House: single-storey (parterowiec) mode + przedsionek-entry semantics

**Status:** approved (brainstorm 2026-06-03, Dawid).
**Supersedes/expands:** the "Phase 3 — Single-storey mode" outline in
`2026-06-02-stage4-open-plan-house-furniture-design.md` (that outline covered only the smallest 35 m²
tier — "no wiatrolap, no separate kitchen"; this spec scales the program by area).
**Builds on:** phase 2b native L-capable hol (`e0bcb23`), S19 open-plan day zone, S17 configurable
`HouseProgramConfig`.

## Why
The house generator only does 2-storey (`generate_house` ignores its `num_storeys` param and always solves
parter + pietro). Dawid's priority is **parterowce first, then furniture**. Two needs:
1. **Single-storey houses** — small/low-end (35 m²) up to full programs on one floor, no stairs.
2. **Correct przedsionek (vestibule) entry semantics** — Dawid: *if a przedsionek appears, the front door
   is IN the przedsionek and from the przedsionek you enter the hol behind it*. Today the entry POINT is
   pinned into the hub (`entry_idx = hub_idx`), and phase 2b only forced the wiatrołap onto the entry
   WALL (beside the door, not containing it). This is wrong and applies to the existing 2-storey path too.

## Decisions (from brainstorm 2026-06-03)
- **D1 — storey count:** explicit input `num_storeys ∈ {1,2}`; a smart default is *suggested* from
  footprint area, architect overrides. (UI-ready toggle.)
- **D2 — przedsionek by area threshold:** footprint **< ~50 m² → no przedsionek** (front door straight
  into the hol); **≥ ~50 m² → przedsionek** (door → przedsionek → hol).
- **D3 — program scales via the S17 engine:** ONE single-storey template + `HouseProgramConfig`; bedrooms
  and extra rooms scale with area through the proven cap+overflow mechanism (1 bed @35 → 2–3 @70 →
  +master/garderoba @120). Not fixed discrete tiers.
- **D4 — przedsionek-entry fix is foundational and in-scope here**, applied to BOTH single- and two-storey
  for consistency (it also corrects the shipped 2-storey path).
- **Thresholds are start values, easy to tune:** przedsionek ~50 m², storey-default ~60 m² footprint,
  `MIN_SINGLE_STOREY_AREA` **~45 m²** (revised 2026-06-03 from ~32 — see D5).
- **D5 — v1 floor is ~45 m², micro-35 deferred (Dawid 2026-06-03):** the standard template
  `min_powierzchnia` (salon 20, kuchnia 7, sypialnia_1 11, lazienka 2.5, hub 4 → ~44.5 m² for the minimal
  day-zone + 1 bed + bath + hol) make a 35 m² single-storey INFEASIBLE (F3 mins can't be lowered). v1
  targets single-storey **≥ ~45 m²** with standard mins (bedrooms scale 1→2→3→+master). The micro-35 tier
  (reduced mins: salon ~15, open kitchenette, no hol/wc) is a separate small follow-up.

## Design

### Section 1 — Entry / przedsionek semantics (fix; 1- and 2-storey)
- **Przedsionek present:** call `solve_cpsat(..., entry_room_id="wiatrolap")`. Then the existing entry
  block (`cpsat_solver.py` ~516–537, gated `hub_at_entry and entry_idx is not None`) constrains the
  **wiatrołap** (not the hub) to *contain the entry point* and *touch the entry wall*. The hub is freed
  from the entry wall and only stays adjacent to the wiatrołap (template adjacency wiatrołap↔hol) → "enter
  through the przedsionek into the hol behind it".
- **Remove the now-redundant** phase-2b wiatrołap-wall block (the `wiat_idx` forcing added in
  `e0bcb23`): with `entry_idx = wiatrołap` the existing block already does it. Keep the WC-external block.
- **No przedsionek (small house):** `entry_room_id=None` → `entry_idx = hub_idx` → hub contains the door +
  touches the entry wall (enter straight into the hol). This is the current behaviour, unchanged.
- **Feasibility-delicate** (changes which room is pinned to the entry wall; session-18 lesson). **TDD
  RED-first** across the footprint × entry-side matrix BEFORE the fix; 2 fails ⇒ rewrite (B1).

### Section 2 — Template `templates/house_single_storey.json`
- Rooms: `hub` (hol) + `wiatrolap` + `salon` + `kuchnia` (+`spizarnia`) + `wc` + `lazienka` +
  `sypialnia_1..N` (+`garderoba`, +`kotlownia` by size). **No `schody`.**
- F5 hub-centric star (every room ↔ hol); day-zone open-plan (salon+kuchnia as one DZIENNA space, S19);
  master = `sypialnia_1`. Adjacency graph defined in the template.
- Mirrors the `house_parter.json` / `house_pietro.json` pattern (one new file, no schema change).

### Section 3 — Single-storey program (`HouseProgramConfig`)
- `default_house_config(storey="single", master_id="sypialnia_1")` — combined day+night caps on one floor;
  bedrooms scale with area via the existing cap + overflow logic (S17). Overflow → bedrooms/day-zone (S19
  rule), never the hol.
- **Conditional rooms by area** (before solving, `generate_house` filters the spec list): drop
  `wiatrolap` below the D2 threshold; the smallest tier may also be open-kitchen only (no separate
  `kuchnia`/`spizarnia`) per the 2026-06-02 outline.

### Section 4 — `generate_house(num_storeys=1)` branch
- No `_reserve_core`, no `schody`, no pietro. One `solve_cpsat` on the single-storey template with
  `program_config` + `entry_room_id` per the D2 przedsionek rule + (likely) `l_capable_ids={"hub"}` so the
  hol can wrap several rooms while staying ≤F4 (see Risk).
- Separate `MIN_SINGLE_STOREY_AREA ≈ 45` (vs `MIN_STOREY_AREA=60` for 2-storey; see D5). Return a layout carrying
  one room set (reuse `TwoStoreyLayout` with empty `pietro_rooms`, or a clearer single-room-set return —
  decide in the plan; keep callers working).
- `suggest_storeys(area_m2) -> int`: 1 if footprint < ~60 m² else 2 (architect overrides). Pure helper,
  UI-ready, does not force anything.

### Section 5 — Testing (RED-first)
- **Feasibility matrix:** single-storey across footprints (≈35/50/70/100) × 4 entry sides → `ok`.
- **Przedsionek present (≥~50):** the wiatrołap polygon *contains the entry point* and touches the entry
  wall; hol adjacent to wiatrołap; you do NOT enter the hol directly.
- **No przedsionek (<~50):** no wiatrołap room; hol contains the entry point / touches the entry wall.
- **Invariants with the engine active:** F1 coverage `==` + no overlap; F4 hol ≤15%; F2 lazienka ≤5,
  wc ≤3; every room ↔ hol ≥0.9 m (F5).
- **Regression:** 2-storey przedsionek-entry now puts the door in the wiatrołap (the phase-2b behavior
  test for wiatrołap-on-wall stays green; add the contains-entry assertion). M1–M5 still model no-op.
- **Storey default:** `suggest_storeys` returns 1 below the threshold, 2 above.

## Risk
In a single-storey house the hol touches MANY rooms (day + night on one star). F4 (hol ≤15%, compact)
vs touching 6–8 rooms can conflict. The phase-2b **L-capable hol** mitigates this (an L arm can reach more
rooms with minimal area); plan should wire `l_capable_ids={"hub"}` for single-storey and verify F4 holds.
If it still conflicts on the largest single-storey footprints, that is a finding to surface, not a reason
to relax F4 (B3).

## Deferred (not in scope)
- **Micro single-storey (~35 m²)** — needs reduced room mins (salon ~15, open kitchenette, no hol/wc); a
  small follow-up after v1 (D5).
- Non-rectangular footprints (L/U/trapezoid) — still gated `notch is None`.
- Furniture (phase 4, next after this).
- Phase 2c scaled 2-storey room-set; bedrooms-as-L; "separate kitchen" toggle.
- "L only when it minimizes the corridor" objective tuning (Dawid option A, furniture phase).

## Open — needs Dawid before touching
- None blocking. Thresholds (50 / 60 / 32) are tunable defaults agreed as start values.
