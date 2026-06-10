"""Przedsionek-entry: gdy wiatrołap istnieje, drzwi wejściowe są W NIM (zawiera punkt
wejścia + dotyka ściany wejścia), a hol jest za nim (sąsiaduje). Dotyczy 1- i 2-kondygnacyjnych."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import generate_house


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


# Obrysy 11×8 (88 m²): knee-wall (S26) wymaga pasa poddasza ≥ programu piętra,
# stare 9×7 (pas 37.8 m²) jest architektonicznie za małe na dom 2-kond.
@pytest.mark.parametrize("W,H,ex,ey,side", [
    (11.0, 8.0, 5.5, 0.0, "south"),
    (11.0, 8.0, 0.0, 4.0, "west"),
    (11.0, 8.0, 11.0, 4.0, "east"),
    (11.0, 8.0, 5.5, 8.0, "north"),
])
def test_two_storey_door_is_inside_wiatrolap(W, H, ex, ey, side):
    layout = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), (ex, ey),
                            num_storeys=2, time_limit_s=45.0)
    assert layout.ok, layout.message
    wiat = _room(layout.parter_rooms, "wiatrolap")
    hub = _room(layout.parter_rooms, "hub")
    b = wiat.polygon.bounds  # (minx, miny, maxx, maxy)
    # wiatrołap zawiera punkt drzwi w poziomie/pionie wejściowej ściany
    if side in ("south", "north"):
        assert b[0] - 1e-6 <= ex <= b[2] + 1e-6, f"wiatrołap nie obejmuje drzwi x={ex}: {b}"
        assert (abs(b[1]) < 0.05) if side == "south" else (abs(b[3] - H) < 0.05)
    else:
        assert b[1] - 1e-6 <= ey <= b[3] + 1e-6, f"wiatrołap nie obejmuje drzwi y={ey}: {b}"
        assert (abs(b[0]) < 0.05) if side == "west" else (abs(b[2] - W) < 0.05)
    # hol za przedsionkiem: sąsiaduje wspólną krawędzią ≥0.9 m
    shared = wiat.polygon.boundary.intersection(hub.polygon.boundary).length
    assert shared >= 0.9 - 1e-6, f"hol nie za przedsionkiem (krawędź {shared:.2f} < 0.9)"
