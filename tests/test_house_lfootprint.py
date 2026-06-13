"""L-footprinty domów 2-kond. (S30, decyzja Dawida 2026-06-13): rdzeń klatki
kotwiczony przy WEWNĘTRZNYM narożniku skrzydeł, nie w wcięciu L.
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


@pytest.mark.parametrize("builder,corner", [
    (_L_bottom_right, lambda nf: (nf.x, nf.y + nf.height)),          # dolny-prawy → (nx, ny+nh)
    (_L_top_left,     lambda nf: (nf.x + nf.width, nf.y)),           # górny-lewy → (nx+nw, ny)
])
def test_core_at_inner_corner(builder, corner):
    """Jeden róg rdzenia styka się z wklęsłym wierzchołkiem L."""
    poly = builder()
    b = analyze_boundary(poly, entry_point=(6.0, 5.0))
    assert b.notch is not None
    cx, cy, sw, sh = _reserve_core(b.bbox, (6.0, 5.0), force_straight=True, notch=b.notch)
    ix, iy = corner(b.notch)
    corners = [(cx, cy), (cx + sw, cy), (cx, cy + sh), (cx + sw, cy + sh)]
    dmin = min((abs(px - ix) + abs(py - iy)) for px, py in corners)
    assert dmin < 0.05, f"żaden róg rdzenia {corners} nie przy wklęsłym wierzchołku ({ix},{iy})"


def test_reserve_core_rectangle_unchanged():
    """notch=None → wynik IDENTYCZNY jak bez parametru (gwarancja braku regresji)."""
    for bbox, entry in [((0, 0, 10, 8), (5, 0)), ((0, 0, 9, 7), (0, 3.5)),
                        ((0, 0, 11, 8), (5.5, 8)), ((0, 0, 8, 10), (8, 5))]:
        assert _reserve_core(bbox, entry, force_straight=True) == \
               _reserve_core(bbox, entry, force_straight=True, notch=None)
