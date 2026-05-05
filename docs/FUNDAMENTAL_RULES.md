# FUNDAMENTAL_RULES — absolute priority

> **These rules are NON-NEGOTIABLE.** During the C++ session of 2026-04-25
> in FloorPlan4_CPP they were repeatedly broken — that was the root cause of
> the disaster (25+ regression commits, 4 failed approaches, bathroom 13 m²
> instead of 5).
>
> **Before EVERY code change:** read this file. If you want to change
> anything that violates these rules — STOP and ask the project owner
> EXPLICITLY.

---

## ARCHITECTURAL RULES (WT and layout) — ABSOLUTE

### F1 — 100 % outline coverage
**The user's polygon = the apartment. ENTIRELY. No exceptions.**

- Solver result MUST fill the whole polygon
- Coverage = `sum(rooms_areas) == usable_area_cm2` (EQUALITY, not inequality!)
- NO "virtual obstacles" reducing usable area
- NO gaps > 0 m²
- NO "rectangles from nowhere" (extra_rect detached from the main room)

**Violated in C++ session:** 15 % holes, detached rectangles.

**In Python:** `core/cpsat_solver.py:253` — `model.add(sum(areas) == usable_area)`.
This is sacred — do not change to `<=`.

### F2 — Bathroom max 5 m² (WT — hard cap)
**The bathroom CAN NEVER exceed 5 m². Regardless of apartment type, outline
size or any other circumstance.**

- WT min: 175 × 250 cm clear dimensions
- WT max: **5.0 m² absolute**
- WT max dimension: 3 m
- The bathroom MUST be rectangular (sanitary installations)
- The bathroom does NOT absorb overflow / extra area

**Violated in C++ session:** 5.4–13.1 m² multiple times. This was BUG #1
fixed in the first FloorPlan6 session — see `docs/STATE.md`.

### F3 — WT `min_powierzchnia`, `min_szerokosc` — never lower
**Rules from WT 2002 are LEGAL thresholds. They cannot be lowered "to
make the solver find a solution".**

- `min_powierzchnia` (e.g. living room M1: 25 m², bedroom 2-person: 9 m²) — RIGID
- `min_szerokosc` (e.g. living room: 3.2 m, bathroom: 1.5 m) — RIGID
- Service rooms must satisfy bathroom min (1.5 m × 2.5 m)

**If solver INFEASIBLE with these rules → change the template, do NOT lower
the thresholds.**

### F4 — Hub: compact, NOT a spine
**Hub is a central hallway, NOT a narrow corridor.**

- Hub max 15 % of usable area
- Hub max aspect ratio 1.5 (NOT a long narrow strip)
- Hub max 60 % of BW and 60 % of BH (NOT full width/height)
- Hub contains the entry_point
- Hub touches EVERY room (adjacency edge ≥ 90 cm)

### F5 — Topology through the hub
**All rooms accessible through the hub. No direct room↔room connections.**

- Exception: bathroom↔bedroom only when there is more than one bathroom (M4+)
- Adjacency from the template = direct shared edge ≥ 90 cm

### F6 — Facade: rooms requiring windows touch the polygon edge
**Rooms with `wymaga_okna=true` must touch a FACADE edge of the polygon
(not a bbox side).**

- Living room, bedroom, kitchen → require facade
- Bathroom, hub, walk-in closet → may be internal
- Detection: real polygon edge, NOT bbox approximation

### F7 — Room aspect ratio MAX 2.5
**No room can be longer than 2.5 × its width.**

- Optimal: 1.0–2.0
- Tolerated: up to 2.5
- Above: room becomes a "channel" — non-functional

### F8 — Doors and walls
- One wall per shared edge between two rooms
- Wall reference line = CENTER
- Doors: rooms open INWARD, bathrooms outward
- Entry door: outward of the apartment
- Door leaf swings towards the nearest perpendicular wall
- Hub↔living room/kitchenette joint → empty opening of full width
- Two bathrooms ONLY in M4+

### F9 — Facade detection
**A different composite = exterior wall (FACADE).** Detection per actual
polygon edge, not bbox side.

### F10 — Post-clip validator = 100 % strict
**Validator MUST check both MIN and MAX. No soft tolerances.**

- `min_powierzchnia` → reject if room < min
- `min_szerokosc` → reject if width < min
- **MAX area (bathroom 5 m²) → reject if > max** ⚠️ THIS WAS FORGOTTEN in C++
- `pct_max × usable` → reject if > limit
- Room 1 cm below WT or 1 cm above max = variant rejected

**In Python:** `core/validator.py` — check that MAX assertions exist. If not,
add as the first task.

---

## WORKFLOW RULES (CLAUDE behavior) — ABSOLUTE

### B1 — After 2 failed attempts → REWRITE, not a 3rd iteration
**This is absolute. Non-negotiable.**

- 1 fail → root-cause diagnosis
- 2 fails → STOP, rewrite the module from scratch with a different approach
- 3rd attempt → FORBIDDEN

**Violated in C++ session:** 14 patches in one area (PolygonFiller). 4 failed
architectural approaches.

### B2 — Plain-language plan BEFORE changing code
**Always. Even for a 1-line change.**

- What I want to change (architecturally, not programmatically)
- Why (root cause)
- How the result will change (what the user will see)
- **Wait for the user's OK**

### B3 — Do NOT change the rules to make the solver work
**WT, layout and scoring rules are RIGID. Solver doesn't find a solution →
change the approach, NOT the rule.**

- "Threshold too strict" → you're misinterpreting the threshold, do NOT lower
- "Solver INFEASIBLE" → look for another template / approach, do NOT relax the constraint
- "pct_max cap too low" → memory allows LEVEL 1 (fill) > LEVEL 2 (caps), but the
  BATHROOM 5 m² cap is a WT hard cap — still absolute

### B4 — Do NOT propose rule-violating options
**Even as a fallback / last resort.**

- If all options violate a rule → "I see no solution without violating X" + wait
- Do NOT list options like "lower threshold to X% as a compromise"

### B5 — Ask about architectural decisions, NOT obvious things
- Do NOT ask: "is the polygon the apartment?" (YES, always, by definition)
- DO ASK: "who absorbs the excess — living room or bedroom?"
- DO ASK: "bathroom on facade or internal in this case?"

### B6 — Listen to the user literally
- "Fill the entire outline" = FILL THE ENTIRE OUTLINE, do not interpret as
  "they didn't really mean it"
- "Don't change X" = DO NOT CHANGE X, end of discussion

### B7 — Translate architecturally, not programmatically
- ❌ "AddEquality(area_sum, usable_area)"
- ✅ "Solver requires that the sum of room areas EXACTLY equals the outline area"
- The user is an architect, I am a programmer — communicate in their language

### B8 — Verify before "done"
**Never report "fixed" / "works" without:**
1. `pytest tests/` green
2. Manual run via `python main.py` or notebook
3. Matplotlib visualisation showing the result
4. User retest showing the result

### B9 — Memory-driven — remember, don't invent
- Rules are in FloorPlan6 docs/
- Read `docs/` AT THE START of every session
- Rule in docs → respect it. Rule not in docs BUT user gave it → save it
  IMMEDIATELY to `docs/OPEN_QUESTIONS.md` or the appropriate doc

### B10 — Communication: peer-to-peer (in Polish)
- No "Mr / Mrs"
- We are partners
- Professional but familiar
- Polish by default (user preference)
- Concise, honest, objective — don't say what the user wants to hear

---

## ADAPTATION TO PYTHON

In FloorPlan6 (Python), specifically remember:

### P1 — `Coverage equality` — `cpsat_solver.py`
In FP4 Python `core/cpsat_solver.py:140` it was
`model.Add(sum(areas) == usable_area_cm2)`. Verify it's still the case.
Do NOT change to `<=`.

### P2 — `scale=100` (centimetres)
All CP-SAT values are integer cm. Do NOT go back to floats. Eliminates a
class of bugs like "0.999 != 1.0".

### P3 — Visualisation from minute one
`viz/plan_renderer.py` exists. After EVERY solver change — render PNG and
look at it. Geometric debugging without a drawing is impossible.

### P4 — Regression tests for F2 and F10
In `tests/test_cpsat_solver.py` add or ensure that this exists:
```python
def test_lazienka_never_exceeds_5m2():
    """F2: bathroom NEVER > 5 m². Test must pass for all templates × all outlines."""
    for template_id in ["M2_standard", "M3_standard", "M3_wc",
                        "M4_standard", "M4_2laz", "M5_standard"]:
        for (w, h) in [(6, 6), (8, 6), (10, 8), (12, 10), (15, 12)]:
            ...
            for room in result.rooms:
                if "lazienka" in room.spec.id.lower() or "wc" in room.spec.id.lower():
                    assert room.area <= 5.0, \
                        f"F2 violation: {template_id} {w}×{h}: {room.spec.id}={room.area:.2f}m²"
```

---

## CHECKLIST BEFORE EVERY CODE CHANGE

```
[ ] I read this FUNDAMENTAL_RULES.md TODAY
[ ] I checked the change does NOT violate F1–F10 (architecture) or B1–B10 (workflow)
[ ] Plain-language plan presented to the user (in Polish)
[ ] Got explicit OK (or the change is trivially within clear consent)
[ ] This is the first or second attempt (NOT the third)
[ ] I have root-cause diagnosis (if it's a fix)
[ ] I know how I'll verify the result (pytest, manual run, viz)
```

**If any item = NO → STOP, do not change the code.**

---

## CONFLICT HIERARCHY

When rules conflict (rare, but it happens):

1. **WT and layout (F1–F10)** — highest priority (law + architectural rules)
2. **B1 (don't patch)** — if it repeats, the problem is fundamental
3. **User decision** — when F and B don't resolve, the user decides
4. **LEVEL 1 (fill polygon) > LEVEL 2 (caps pct_max)** — authorised 2026-04-22,
   but the **BATHROOM 5 m² cap is a WT cap, not pct_max** — still absolute

---

## EXAMPLES OF VIOLATIONS FROM C++ SESSION (DO NOT REPEAT IN PYTHON)

| # | Rule violated | What I did | Consequence |
|---|---------------|------------|-------------|
| 1 | F2 (5 m²) + B3 (don't change rules) | Changed 70 % facade ratio to "1 m absolute" without OK | Bathroom grew to 13 m² |
| 2 | B1 (2 fails → rewrite) | 14 patches to pre-assign cells (ceil/floor → round → strict) | Time wasted, regressions |
| 3 | F1 (100 % coverage) | Changed `==` to `<=` in solver | 15 % holes in polygon |
| 4 | F2 (bathroom rectangle) + F1 | absorbUncoveredPolygon produced detached extra_rect | "Rectangles from nowhere" |
| 5 | F10 (validator MAX) | Validator did not check MAX | Bathroom 8–13 m² passed validation |
| 6 | B2 (plan before change) | Edited code without a plan | Multiple regressions |
| 7 | B6 (listen literally) | Interpreted "don't touch" as "modify slightly" | User frustration |

---

## SUMMARY ONE-LINER

**The rules are inviolable. If you feel tempted to change them — STOP, ask.
Patching never works. 2 fails = rewrite.**

— These rules save the project. Breaking them destroyed the 25 April C++ session.
