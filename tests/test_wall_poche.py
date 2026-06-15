"""Poché ścian — geometryczny rdzeń (viz/plan_renderer._wall_poche_polygon)."""
from shapely.geometry import box, Point

from viz.plan_renderer import _wall_poche_polygon


def test_wall_poche_has_seam_between_two_rooms():
    boundary = box(0, 0, 6, 4)
    left = box(0, 0, 3, 4)
    right = box(3, 0, 6, 4)
    wall = _wall_poche_polygon(boundary, [left, right], w_ext=0.30, w_int=0.12)
    assert wall.area > 0
    assert boundary.buffer(1e-6).contains(wall)
    # punkt na wewnętrznej fudze (x=3) leży w ścianie
    assert wall.buffer(1e-9).contains(Point(3.0, 2.0))
    # środek każdego pokoju NIE leży w ścianie (to wnętrze, nie ściana)
    assert not wall.contains(Point(1.5, 2.0))
    assert not wall.contains(Point(4.5, 2.0))


def test_wall_poche_exterior_ring_present():
    boundary = box(0, 0, 6, 4)
    room = box(0, 0, 6, 4)                       # jeden pokój = cały obrys
    wall = _wall_poche_polygon(boundary, [room], w_ext=0.30, w_int=0.12)
    # bez wewnętrznych fug zostaje sam pierścień zewnętrzny — punkt przy krawędzi w ścianie,
    # środek wolny
    assert wall.buffer(1e-9).contains(Point(0.10, 2.0))
    assert not wall.contains(Point(3.0, 2.0))
