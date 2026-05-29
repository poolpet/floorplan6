from core.cpsat_solver import solve_cpsat, SCALE
from core.template_selector import load_all_templates
from core.boundary_analyzer import analyze_boundary
from shapely.geometry import Polygon


def _rect_boundary(w=10.0, d=8.0):
    poly = Polygon([(0, 0), (w, 0), (w, d), (0, d)])
    return analyze_boundary(poly, entry_point=(w / 2, 0.0))


def _template(tid="M3_standard"):
    return next(t for t in load_all_templates() if t.id == tid)


def test_reserved_core_none_is_unchanged():
    b = _rect_boundary()
    t = _template()
    r1 = solve_cpsat(t, b, time_limit_s=10.0)
    r2 = solve_cpsat(t, b, time_limit_s=10.0, reserved_core=None)
    assert r1.status == r2.status
    assert len(r1.rooms) == len(r2.rooms)


def test_reserved_core_is_inside_hub():
    b = _rect_boundary()
    t = _template()
    core = (4.0, 0.0, 2.5, 3.0)  # x, y, w, h metres, bbox-relative
    r = solve_cpsat(t, b, time_limit_s=15.0, reserved_core=core)
    assert r.status in ("OPTIMAL", "FEASIBLE")
    hub = next(room for room in r.rooms if "hub" in room.spec.id)
    hb = hub.polygon.bounds
    cx, cy, cw, ch = core
    tol = 0.05
    assert hb[0] <= cx + tol and hb[2] >= cx + cw - tol
    assert hb[1] <= cy + tol and hb[3] >= cy + ch - tol
