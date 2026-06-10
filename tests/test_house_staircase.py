"""Adaptive staircase core geometry + position (Approach A, Session 16)."""
from core.house_layout import _stair_core_dims, STAIR_MAX_AREA


def test_square_outline_gives_u_stair():
    sw, sh, kind = _stair_core_dims(8.0, 8.0)
    assert kind == "u"
    assert abs(sw - sh) < 1e-6            # zwarty kwadrat
    assert 2.0 <= sw <= 2.6
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_wide_outline_gives_straight_run_along_x():
    sw, sh, kind = _stair_core_dims(11.0, 6.0)
    assert kind == "straight"
    assert sw > sh                        # bieg wzdłuż dłuższej osi (X)
    assert sh <= 1.3                      # wąski bieg
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_deep_outline_gives_straight_run_along_y():
    sw, sh, kind = _stair_core_dims(6.0, 11.0)
    assert kind == "straight"
    assert sh > sw                        # bieg wzdłuż dłuższej osi (Y)
    assert sw <= 1.3
    assert sw * sh <= STAIR_MAX_AREA + 1e-6


def test_core_area_never_exceeds_cap_or_40pct():
    for W, H in [(8, 8), (11, 6), (6, 11), (9, 7), (7.8, 7.8), (12, 7)]:
        sw, sh, _ = _stair_core_dims(W, H)
        assert sw * sh <= STAIR_MAX_AREA + 1e-6
        assert sw <= 0.40 * W + 1e-6
        assert sh <= 0.40 * H + 1e-6


from core.house_layout import _reserve_core, STAIR_FRONT_SETBACK


def _core_for(W, H, entry):
    return _reserve_core((0.0, 0.0, W, H), entry)


def test_core_is_set_back_from_south_entry():
    """Approach B: rdzeń cofnięty ~STAIR_FRONT_SETBACK od ściany wejścia (hol z przodu)
    i odsunięty do ściany bocznej (offset w X)."""
    cx, cy, sw, sh = _core_for(8.0, 8.0, (4.0, 0.0))
    assert abs(cy - STAIR_FRONT_SETBACK) < 0.3   # cofnięty od frontu o ~1.8 m
    assert cx < 1e-6 or abs(cx + sw - 8.0) < 1e-6  # przy ścianie bocznej (W lub E)
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_is_set_back_from_west_entry():
    """Approach B: dla wejścia od zachodu rdzeń cofnięty ~STAIR_FRONT_SETBACK w X."""
    cx, cy, sw, sh = _core_for(8.0, 8.0, (0.0, 4.0))
    assert abs(cx - STAIR_FRONT_SETBACK) < 0.3
    assert cy < 1e-6 or abs(cy + sh - 8.0) < 1e-6  # przy ścianie poziomej (S lub N)
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_inside_bbox_for_all_entries():
    for entry in [(4.0, 0.0), (4.0, 8.0), (0.0, 4.0), (8.0, 4.0)]:
        cx, cy, sw, sh = _core_for(8.0, 8.0, entry)
        assert cx >= -1e-6 and cy >= -1e-6
        assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_generate_house_feasible_and_schody_separate_from_hol():
    """Approach B: generate_house feasible; rdzeń klatki należy do OSOBNEGO pokoju
    'schody' (a NIE do holu), a hol parteru jest kompaktowy (przedsionek, nie 'Hol+schody').
    Obrys 10×8 (knee-wall S26: pas poddasza musi pomieścić program piętra; 8×8 za małe);
    dom 2-kond. = bieg prosty wzdłuż kalenicy (force_straight)."""
    from shapely.geometry import Polygon, box
    from core.house_layout import generate_house
    from core.models import Strefa
    layout = generate_house(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), (5.0, 0.0),
                            time_limit_s=45.0)
    assert layout.ok, layout.message
    sw, sh, _ = _stair_core_dims(10.0, 8.0, force_straight=True)
    core_area = sw * sh
    cx, cy, csw, csh = layout.stair_core
    core_box = box(cx, cy, cx + csw, cy + csh)
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        schody = next(r for r in rooms
                      if r.spec.id == "schody" and r.spec.strefa == Strefa.KOMUNIKACJA)
        hol = next(r for r in rooms if r.spec.id == "hub" and r.spec.strefa == Strefa.KOMUNIKACJA)
        assert abs(schody.area - core_area) < 0.25     # schody == rdzeń klatki (pinned)
        assert not hol.polygon.contains(core_box.buffer(-0.02))  # hol NIE zawiera rdzenia
    # hol parteru kompaktowy (dawny scalony hub puchł >12 m²; 13% usable = anty-bloat)
    hol_p = next(r for r in layout.parter_rooms if r.spec.id == "hub")
    assert hol_p.area <= 0.13 * 80.0
