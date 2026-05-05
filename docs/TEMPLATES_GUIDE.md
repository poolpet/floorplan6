# TEMPLATES_GUIDE — three template sets

> **Context:** during work on previous versions THREE different "template"
> sets were created. Each has a different purpose. Mixing them up = bugs and
> wasted time.

---

## WHERE THESE THREE SETS COME FROM

In FloorPlan2 and early FloorPlan4 there was only 1 set — hand-written
rules. Over time two more were added:
- **Set 2** — to train/validate the solver against real apartments
- **Set 3** — with the adjacency graph filled in (for the template_selector
  trying to find a plan similar to the user's outline)

In FloorPlan4_CPP only Set 1 (constraints) was copied. FloorPlan6 has all three.

---

## SET 1: CONSTRAINT TEMPLATES (`templates/`) — 7 files

**Location:** `FloorPlan6/templates/M*.json`

**Schema:**
```json
{
  "id": "M3_standard",
  "nazwa": "3-room standard",
  "typ_mieszkania": "M3",
  "pokoje": [
    {
      "id": "hub",
      "nazwa": "Hallway",
      "strefa": "KOMUNIKACJA",
      "wymaga_okna": false,
      "priorytet_fasady": null,
      "min_powierzchnia": 5.0,
      "opt_powierzchnia": 8.1,
      "min_szerokosc": 1.2,
      "max_proporcja": 2.0,
      "procent_powierzchni": [0.08, 0.15]
    },
    ...
  ],
  "sasiedztwo": [
    {"room_a": "hub", "room_b": "_outside", "connection_type": "entry_door"},
    {"room_a": "hub", "room_b": "lazienka", "connection_type": "door"},
    ...
  ]
}
```

**Contains:** RULES (constraints) — what MUST be in an apartment of a given
type. **No geometry.**

**Room fields:**
- `min_powierzchnia` / `opt_powierzchnia` (m²)
- `min_szerokosc` (m)
- `max_proporcja` (aspect ratio)
- `procent_powierzchni` `[min%, max%]` relative to usable area
- `wymaga_okna` (bool)
- `priorytet_fasady` (int, lower = higher priority)
- `preferowana_orientacja` (cleared in 2026-05-04 — kept as empty list for
  backward compat; not used by the scorer)

**Adjacency fields:**
- `room_a`, `room_b` (room id or `"_outside"`)
- `connection_type`: `"entry_door"` / `"door"` / `"opening"`

**Files (7):**
| File | Type | Rooms | Notes |
|------|------|-------|-------|
| M1_standard.json | M1 | 4 (hub, bathroom, bedroom, living/kitchenette) | min |
| M2_standard.json | M2 | 4 (hub, bathroom, bedroom, living/kitchenette) | |
| M3_standard.json | M3 | 5 (+ bedroom_2) | |
| M3_wc.json | M3 | 6 (+ wc) | for outlines with room for a separate WC |
| M4_standard.json | M4 | 6 | |
| M4_2laz.json | M4 | 7 (+ 2nd bathroom) | two bathrooms only in M4+ (F8) |
| M5_standard.json | M5 | 7-8 | max |

**Used by:**
- `core/cpsat_solver.py` uses these constraint templates to generate new layouts
- `core/template_selector.py` selects candidates based on apartment type and
  outline size
- `core/validator.py` checks the solver result against the constraints

**When to use:** **ALWAYS in the generation pipeline.**

---

## SET 2: TRACED REAL APARTMENTS — without filled adjacency graph

> **Status in FloorPlan6:** NOT COPIED (they were in FP4 `rzuty/templates/`,
> 41 files, edges are `-1` placeholders).
>
> **Source:** `FloorPlan4/rzuty/templates/PL_*.json` (41 files).
> **In FP6:** `rzuty/` folder is empty — we can import on demand if needed.

**Schema:** similar to Set 3, BUT `edges[].room_a_idx` and `room_b_idx`
fields are all `-1` (placeholder).

**Contains:** room geometry (polygons), facades, stretch — BUT NO
adjacency graph (the graph skeleton is there, the data isn't).

**Use:** rarely. Only when you need GEOMETRY for a room not in Set 3
(14 such: PL_NL_16, D14, D24, E11, F34, F40, G53, J25, J27, J41, K40,
PL_TVR_17, 21, 23). Then import on demand from FP4.

---

## SET 3: TRACED REAL APARTMENTS — WITH FILLED GRAPH ⭐ (`data/plans/`)

**Location:** `FloorPlan6/data/plans/PL_*.json` — 27 files.

**Schema:**
```json
{
  "id": "PL_NL_29",
  "original_id": "NL_29",
  "copies": ["NL_08", "NL_13", "NL_16"],
  "total_area_m2": 67.08,
  "width_m": 13.97,
  "height_m": 7.44,
  "aspect_ratio": 1.878,
  "apartment_type": "M3",
  "n_rooms": 5,
  "rooms": [
    {
      "room_type": 5,
      "label": "HOL",
      "polygon": [{"x": 9.528, "y": 1.815}, ...],
      "area_m2": 8.49,
      "facades": [false, false, false, false, false, false],
      "stretch": ["ADAPT", "ADAPT", ...]
    },
    ...
  ],
  "edges": [
    {"room_a_idx": 0, "room_b_idx": -1, "edge_type": "entry_door"},  ← hub → outside
    {"room_a_idx": 0, "room_b_idx": 2, "edge_type": "door"},          ← hub → room 2
    {"room_a_idx": 0, "room_b_idx": 3, "edge_type": "door"},
    {"room_a_idx": 0, "room_b_idx": 1, "edge_type": "door"},
    {"room_a_idx": 0, "room_b_idx": 4, "edge_type": "opening"}        ← hub → living (opening)
  ],
  "entry_position": {"x": 8.86, "y": 5.6},
  "boundary_edges": [...]  ← wall_type per outer edge
}
```

**Contains:** room GEOMETRY + filled adjacency GRAPH + entry_position +
boundary_edges.

**Mapping `room_type` → category:** `data/dataset_loader.py`
(`ROOM_TYPE_TO_CATEGORY`):
- `1` → BEDROOM
- `3` → BATHROOM
- `4` → WC
- `5`/`6` → HUB
- `7` → WALK-IN CLOSET
- `10` → BEDROOM (generic ROOM)
- `13` → LAUNDRY
- `17` → LIVING / KITCHENETTE

**Files (27):**
- 21× PL_NL_* (Natura Life — Wrocław)
- 6× PL_TVR_* (TVR Konopnickiej — Warsaw)

**Edge fields:**
- `room_a_idx`, `room_b_idx` — index in `rooms[]` (or `-1` = outside)
- `edge_type`: `"entry_door"` / `"door"` / `"opening"`

**Stretch fields (how flexible the edge is):**
- `"FIX"` — edge does NOT move (e.g. wall in a bathroom with installations)
- `"STRETCH"` — can be stretched proportionally
- `"ADAPT"` — adapts to neighbour

**Used by:**
1. **Reference dataset** for `core/template_selector.py` — looks for a plan
   with similar geometry (aspect_ratio, area, n_rooms) to the user's outline
2. **Solver validation** — check that the solver, for a given outline,
   generates a layout SIMILAR to the reference
3. **Statistics for constraint templates** — `data/dataset_stats.py` uses
   these 27 to compute statistics (e.g. % of hub area in M3 apartments)

**When to use:** in `template_selector` and when validating solver results.

---

## DECISION: WHEN TO USE WHICH

| Scenario | Set |
|----------|-----|
| Generating a NEW plan from an AC outline | **1** (constraints + solver) |
| Validating that a generated plan makes sense | **1** (validator) + **3** (compare with reference) |
| Looking for the closest real plan to my outline | **3** (template_selector matching) |
| Building stats "how many m² is a typical hub in M2" | **3** (dataset_stats) |
| Need GEOMETRY of a specific FP4 plan not in Set 3 | **2** — import on demand from FP4 |

---

## ANTI-PATTERNS

❌ **Do NOT merge Set 1 with Set 3 in one file.** There were attempts to
build "v3 with constraint and geometry together". They added no value —
different modules need different things.

❌ **Do NOT modify Set 3 by hand.** That's reference data (real traced
apartments). Modification = loss of validator credibility.

❌ **Do NOT use Set 2 as the main graph source** — edges are `-1`
placeholders, NOT real data.

❌ **Do NOT add a new room to a constraint template without updating
`sasiedztwo[]`** — solver requires that the hub touches EVERY room (F4/F5).

---

## SUMMARY

- **`templates/` (7 files)** = constraints, use in solver and validator
- **`data/plans/` (27 files)** = real reference with geometry + graph, use
  in template_selector and dataset_stats
- **`rzuty/` (empty)** = unfinished Set 2 from FP4, import on demand only
  when you need a specific missing plan
