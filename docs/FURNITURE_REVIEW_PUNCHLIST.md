# Furniture phase 4 — adversarial-review punch-list (deferred)

Source: 31-agent adversarial review of `core/furniture.py` (2026-06-06), 24 confirmed findings.
**Already fixed** (commit `32c2490`): #18 product window-blindness, #2 kitchen wall-fallback, #5/#14 dining salon-prefix.
Below = deferred items, ranked. Each is real (verified by an adversarial agent with a coordinate trace).

## High value / realism (Dawid's Session-16 credibility focus)
1. **Center the bed along its wall → enable BOTH nightstands** [#21]. Bed is placed flush in the wall corner (`_place_on_wall`/`_sweep` return the lo-corner), so one flanking nightstand falls outside the region and only ONE is ever placed. Fix: when `wall_len - bed_along ≥ 2·ns`, center the bed along the wall. Reusable centered-placement helper.
2. **Coffee table BETWEEN sofa and TV** [#3,#20]. Currently `_place_fixed` snaps it flush beside the sofa. Fix: target the midpoint of sofa↔TV centroids (or ~0.45 m off the sofa front, spec §3), validate, fall back to `_place_fixed`.
3. **Bathroom ≤5 m²: washbasin gets dropped (bathtub-first greedy)** [#22]. In ~4 m² the bathtub eats the space → `brak miejsca na umywalkę`. Fix: place washbasin+WC BEFORE the bathtub, or a tiny fixed-layout for ≤5 m², or linear-along-one-wall (#8).
4. **Neufert clearances only on the bed; counter/WC/washbasin/coffee are dead `CLEARANCE` keys** [#1,#6,#12,#9]. Spec §3 wants counter ≥1.2 m, WC/washbasin ≥0.6 m, sofa↔coffee ~0.45 m. ⚠️ CAUTION: applying clearance in tight bathrooms over-tightens and can drop fixtures (it was deliberately removed once for this) — make the KEY-piece fit test clearance-aware AND tune, don't just append zones.
5. **TV-windowless vs facing TRADEOFF** [#19]. TV is hard-pinned opposite the sofa even when that wall is a window (glare). Moving it to a windowless perpendicular wall breaks "facing the sofa". **Needs Dawid's call**: glare-on-facing-TV vs non-facing-no-glare.

## Robustness / correctness
6. **L-shaped / notched ROOM polygon → furniture lands in the cavity (outside room), no warning** [#11]. All placers use `room.polygon.bounds` (bbox) via `_inset`. Cheap guard: require `room.polygon.buffer(1e-6).contains(rect)` for non-rectangular rooms. Relevant once corridor-overflow→L-bedrooms lands (see [[feedback_corridor_minimal_lshaped_rooms]]).
7. **`_shared_wall` ignores overlap EXTENT** [#13]. Dining table can be placed where salon & kuchnia are only partially/marginally adjacent. Fix: compute the shared-edge overlap interval `(lo,hi)`, require `hi-lo ≥ table width`, clamp the sweep to it.
8. **`_room_window_walls` CRASHES (not degrades) if ortools missing** [#15]. The lazy `from core.cpsat_solver import _detect_facade_sides` raises ImportError. Wrap in try/except → `set()` (degrade to boundary=None), or extract `_detect_facade_sides` into an ortools-free helper module.
9. **Wardrobe frequently dropped in small/door-adjacent bedrooms** [#23]. It's the last piece needing a 2.0 m run. Allow it to shorten (2.0→1.6→1.2 sliding-door) or use the bed-wall remainder; optionally a low-priority warning.

## Minor / spec-honesty
10. **Kitchen sink never modeled** [#7] — "zlew pod oknem" is docstring-only. Either add a sink Piece as a counter sub-segment centered on the window, or downgrade the spec/docstring to "counter on the window wall".
11. **Bathroom fixtures snap to ANY wall, not linear along ONE** [#8] — pick one installation wall up front, place bathtub→washbasin→WC along it.
12. **Notch gate silently suppresses ALL window awareness** [#17] — emit one informational warning per `furnish_rooms` when `boundary.notch is not None`.
13. **Spec/code wording nits** [#4,#10,#16] — bed "accessible sides" = nightstands + front strip (reword §3); include WC in the bathroom KEY-piece warning branch or document why optional.
