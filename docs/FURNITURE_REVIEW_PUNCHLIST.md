# Furniture phase 4 — adversarial-review punch-list (deferred)

Source: 31-agent adversarial review of `core/furniture.py` (2026-06-06), 24 confirmed findings.
**Already fixed** (commit `32c2490`): #18 product window-blindness, #2 kitchen wall-fallback, #5/#14 dining salon-prefix.
Below = deferred items, ranked. Each is real (verified by an adversarial agent with a coordinate trace).

## High value / realism (Dawid's Session-16 credibility focus)
1. ✅ **DONE (`e2a4ae2`)** — **Center the bed along its wall → both nightstands** [#21]. `_place_on_wall` gained `prefer_center`; `_furnish_bedroom` centers the bed. (Still falls back to corner when the centered position is blocked → 1 nightstand in tight/door-adjacent bedrooms; acceptable.)
2. ✅ **DONE (`c25ac6c`)** — **Coffee table BETWEEN sofa and TV** [#3,#20]. Placed at the sofa↔TV midpoint, long side parallel to the sofa; `_place_fixed` fallback.
3. ✅ **DONE (`1400c7d`)** — **Bathroom: washbasin+WC before bathtub** [#22]. `_furnish_bathroom` prioritizes the essential small fixtures; in ≤5 m² the bathtub is the one dropped (warns), washbasin kept. (Confirmed on a real 4.1 m² bathroom render.)
4. **Neufert clearances only on the bed; counter/WC/washbasin/coffee are dead `CLEARANCE` keys** [#1,#6,#12,#9]. Spec §3 wants counter ≥1.2 m, WC/washbasin ≥0.6 m, sofa↔coffee ~0.45 m. ⚠️ CAUTION: applying clearance in tight bathrooms over-tightens and can drop fixtures (it was deliberately removed once for this) — make the KEY-piece fit test clearance-aware AND tune, don't just append zones. DEFERRED (tuning-risky).
5. ✅ **RESOLVED — WON'T CHANGE (Dawid 2026-06-06)**: **TV stays opposite the sofa even on a window** [#19]. Dawid: facing the TV beats no-glare; curtains/blinds solve glare. Current behavior is correct; do not move the TV off the facing wall.

## Robustness / correctness — ✅ ALL DONE (`5e2bdfb`)
6. ✅ **L/U-room cavity** [#11] — `furnish_rooms` adds the `bbox − polygon` cavity as a keep-clear zone (no-op for rectangles), so furniture stays inside non-rectangular rooms. (v1 = avoid the cavity; constrain-placement into the arms is the richer future fix.)
7. ✅ **`_shared_wall` overlap-extent** [#13] — requires a real shared-edge overlap ≥0.9 m, not just touching bounds; phantom/corner junctions return None.
8. ✅ **`_room_window_walls` ortools guard** [#15] — lazy import wrapped in try/except ImportError → `set()`; a Shapely-only build degrades instead of crashing (matters for the frozen-sidecar bundle path).
9. ✅ **Wardrobe shrink** [#23] — tries 2.0 → 1.6 → 1.2 (sliding-door widths) on every non-bed wall before giving up.

## Minor / spec-honesty
10. **Kitchen sink never modeled** [#7] — "zlew pod oknem" is docstring-only. Either add a sink Piece as a counter sub-segment centered on the window, or downgrade the spec/docstring to "counter on the window wall".
11. **Bathroom fixtures snap to ANY wall, not linear along ONE** [#8] — pick one installation wall up front, place bathtub→washbasin→WC along it.
12. **Notch gate silently suppresses ALL window awareness** [#17] — emit one informational warning per `furnish_rooms` when `boundary.notch is not None`.
13. **Spec/code wording nits** [#4,#10,#16] — bed "accessible sides" = nightstands + front strip (reword §3); include WC in the bathroom KEY-piece warning branch or document why optional.
