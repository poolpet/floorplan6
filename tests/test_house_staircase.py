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


from core.house_layout import _reserve_core, STAIR_SETBACK


def _core_for(W, H, entry):
    return _reserve_core((0.0, 0.0, W, H), entry)


def test_core_is_set_back_from_south_entry():
    cx, cy, sw, sh = _core_for(8.0, 8.0, (4.0, 0.0))
    assert cy > 0.5                       # NIE przy ścianie wejścia (dawniej cy=0)
    assert cy <= STAIR_SETBACK + 0.3
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_is_set_back_from_west_entry():
    cx, cy, sw, sh = _core_for(8.0, 8.0, (0.0, 4.0))
    assert cx > 0.5                       # cofnięte od ściany zachodniej
    assert cx <= STAIR_SETBACK + 0.3
    assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6


def test_core_inside_bbox_for_all_entries():
    for entry in [(4.0, 0.0), (4.0, 8.0), (0.0, 4.0), (8.0, 4.0)]:
        cx, cy, sw, sh = _core_for(8.0, 8.0, entry)
        assert cx >= -1e-6 and cy >= -1e-6
        assert cx + sw <= 8.0 + 1e-6 and cy + sh <= 8.0 + 1e-6
