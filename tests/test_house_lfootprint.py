"""L-footprinty domów 2-kond. (S30, decyzja Dawida 2026-06-13): rdzeń klatki
w litej GŁÓWNEJ BRYLE — w rogu bbox diagonalnie przeciwnym do wcięcia (wewnętrzny
narożnik = gardło cyrkulacji → INFEASIBLE; dowód: notebooks/lcore_placement_probe).
Spec: docs/superpowers/specs/2026-06-13-L-footprint-houses-design.md"""
import pytest
from shapely.geometry import Polygon, box as shbox

from core.boundary_analyzer import analyze_boundary
from core.house_layout import _reserve_core, generate_house


def _L_bottom_right(W=12.0, H=10.0, nw=4.5, nh=4.0):
    """L z wcięciem w dolnym-prawym rogu [W-nw,W]×[0,nh]."""
    return Polygon([(0, 0), (W - nw, 0), (W - nw, nh), (W, nh), (W, H), (0, H)])


def _L_top_left(W=12.0, H=10.0, nw=4.5, nh=4.0):
    """L z wcięciem w górnym-lewym rogu [0,nw]×[H-nh,H]."""
    return Polygon([(0, 0), (W, 0), (W, H), (nw, H), (nw, H - nh), (0, H - nh)])


def _core_box(core):
    cx, cy, sw, sh = core
    return shbox(cx, cy, cx + sw, cy + sh)


def test_core_not_in_notch():
    """Rdzeń nie przecina wcięcia (dziś _reserve_core go tam wstawia → INFEASIBLE)."""
    poly = _L_bottom_right()
    b = analyze_boundary(poly, entry_point=(6.0, 10.0))
    assert b.notch is not None, "notch nie wykryty — test bez sensu"
    core = _reserve_core(b.bbox, (6.0, 10.0), force_straight=True, notch=b.notch)
    notch_box = shbox(b.notch.x, b.notch.y,
                      b.notch.x + b.notch.width, b.notch.y + b.notch.height)
    assert _core_box(core).intersection(notch_box).area < 1e-6, \
        f"rdzeń {core} wpada w notch {notch_box.bounds}"


@pytest.mark.parametrize("builder,exp", [
    (_L_bottom_right, ("left", "top")),     # notch dolny-prawy → rdzeń lewy-górny
    (_L_top_left,     ("right", "bottom")), # notch górny-lewy → rdzeń prawy-dolny
])
def test_core_anchored_opposite_notch(builder, exp):
    """Rdzeń kotwiczony w rogu bbox DIAGONALNIE PRZECIWNYM do notcha (lita bryła,
    z dala od gardła zgięcia). Sonda S30 (lcore_placement_probe): wewnętrzny
    narożnik = INFEASIBLE, róg przeciwny = OPTIMAL."""
    poly = builder()
    b = analyze_boundary(poly, entry_point=(6.0, 5.0))
    assert b.notch is not None
    W = b.bbox[2] - b.bbox[0]
    H = b.bbox[3] - b.bbox[1]
    cx, cy, sw, sh = _reserve_core(b.bbox, (6.0, 5.0), force_straight=True, notch=b.notch)
    xexp, yexp = exp
    if xexp == "left":
        assert cx < 0.05, f"rdzeń nie przy lewej ścianie: cx={cx}"
    else:
        assert abs((cx + sw) - W) < 0.05, f"rdzeń nie przy prawej ścianie: cx+sw={cx + sw}, W={W}"
    if yexp == "bottom":
        assert cy < 0.05, f"rdzeń nie u dołu: cy={cy}"
    else:
        assert abs((cy + sh) - H) < 0.05, f"rdzeń nie u góry: cy+sh={cy + sh}, H={H}"


def test_reserve_core_rectangle_unchanged():
    """notch=None → wynik IDENTYCZNY jak bez parametru (gwarancja braku regresji)."""
    for bbox, entry in [((0, 0, 10, 8), (5, 0)), ((0, 0, 9, 7), (0, 3.5)),
                        ((0, 0, 11, 8), (5.5, 8)), ((0, 0, 8, 10), (8, 5))]:
        assert _reserve_core(bbox, entry, force_straight=True) == \
               _reserve_core(bbox, entry, force_straight=True, notch=None)


def test_l_2storey_generates():
    """L 102 m² 2-kond. generuje oba piętra (dziś parter+pietro=UNKNOWN)."""
    poly = _L_bottom_right()  # 12×10 − 4.5×4 = 102 m²
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, f"L 2-kond. nie wygenerowana: {lay.message}"
    assert lay.parter_rooms and lay.pietro_rooms


def test_stairs_vertically_aligned_on_L():
    """Schody parteru i poddasza mają ten sam bbox (piony klatki)."""
    poly = _L_bottom_right()
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=2, time_limit_s=60.0)
    assert lay.ok, lay.message
    sp = next(r for r in lay.parter_rooms if r.spec.id == "schody")
    spp = next(r for r in lay.pietro_rooms if r.spec.id == "schody")
    for a, b in zip(sp.polygon.bounds, spp.polygon.bounds):
        assert abs(a - b) < 0.05, f"piony schodów rozjechane: {sp.polygon.bounds} vs {spp.polygon.bounds}"


def test_single_storey_L_still_ok():
    """Regression-lock: parterowiec L (działał przed zmianą) nadal generuje program."""
    poly = _L_bottom_right()
    lay = generate_house(poly, entry_point=(6.0, 10.0), num_storeys=1, time_limit_s=60.0)
    assert lay.ok, lay.message
    beds = [r for r in lay.parter_rooms if r.spec.id.startswith("sypialnia")]
    assert len(beds) >= 3, f"parterowiec L: tylko {len(beds)} sypialni"
