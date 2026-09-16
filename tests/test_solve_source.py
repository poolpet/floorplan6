"""`/solve`: zrodlo obrysu (selection|point|polygon), obrys-only i ksztalt wyniku."""
import pytest
from shapely.geometry import Polygon

RECT = [[0, 0], [8, 0], [8, 6], [0, 6]]


def _fake_plan():
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan
    from core.template_selector import load_all_templates
    tpl = next(t for t in load_all_templates() if t.id == "M2_standard")
    return FloorPlan(boundary=analyze_boundary(Polygon(RECT), (4.0, 0.0)), template=tpl, rooms=[], score=0.9)


def test_polygon_source_boundary_only_when_zero_variants(monkeypatch):
    import service.solve_adapter as sa
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: pytest.fail("solver must not run"))
    out = sa.solve_request({"mode": "apartment", "source": "polygon", "polygon": RECT, "entry": [4, 0], "max_variants": 0})
    assert out["variants"] == []
    b = out["boundary"]
    assert b["area"] == pytest.approx(48.0) and b["auto_type"] == "M2" and b["entry"] == [4.0, 0.0]
    assert len(b["polygon"]) >= 4


@pytest.mark.parametrize("area, mtype", [(40, "M1"), (48, "M2"), (70, "M3"), (100, "M4"), (130, "M5")])
def test_auto_type_thresholds(area, mtype):
    from service.solve_adapter import auto_type_for_area
    assert auto_type_for_area(area) == mtype


def test_selection_source_uses_boundary_reader(monkeypatch):
    import service.solve_adapter as sa
    from core.models import WallType
    monkeypatch.setattr(sa, "read_boundary_from_archicad",
                        lambda tapir=None: (Polygon(RECT), (4.0, 0.0), [WallType.FACADE] * 4))
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: [_fake_plan()])
    out = sa.solve_request({"mode": "apartment", "source": "selection", "mtype": "M2", "max_variants": 1})
    assert out["boundary"]["auto_type"] == "M2"
    assert out["variants"][0]["index"] == 0 and out["variants"][0]["score"] == 0.9
    assert "rooms" in out["variants"][0]["contract"]


def test_point_source_passes_coordinates(monkeypatch):
    import service.solve_adapter as sa
    seen = {}
    def fake(x, y, tapir=None):
        seen.update(x=x, y=y); return (Polygon(RECT), (4.0, 0.0), None)
    monkeypatch.setattr(sa, "read_boundary_from_point", fake)
    out = sa.solve_request({"mode": "apartment", "source": "point", "point": [3.5, 2.0], "max_variants": 0})
    assert seen == {"x": 3.5, "y": 2.0} and out["boundary"]["area"] == pytest.approx(48.0)


def test_store_receives_plans(monkeypatch):
    import service.solve_adapter as sa
    from service.results import ResultStore
    monkeypatch.setattr(sa, "generate_variants", lambda *a, **k: [_fake_plan()])
    store = ResultStore()
    sa.solve_request({"mode": "apartment", "source": "polygon", "polygon": RECT, "entry": [4, 0], "mtype": "M2",
                      "max_variants": 1, "_job_id": "j1"}, store=store)
    e = store.get("j1")
    assert e["mode"] == "apartment" and len(e["plans"]) == 1 and e["plans"][0].score == 0.9


def test_house_result_shape(monkeypatch):
    import service.solve_adapter as sa
    monkeypatch.setattr(sa, "generate_house", lambda p, e, **kw: "LAYOUT")
    monkeypatch.setattr(sa, "house_to_contract", lambda layout: {"parter": {"rooms": []}, "poddasze": {"rooms": []}})
    out = sa.solve_request({"mode": "house", "source": "polygon", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]], "entry": [5, 0]})
    assert out["variants"] == [{"index": 0, "score": None, "contract": {"parter": {"rooms": []}, "poddasze": {"rooms": []}}}]


def test_unknown_source_is_value_error():
    import service.solve_adapter as sa
    with pytest.raises(ValueError, match="source"):
        sa.solve_request({"mode": "apartment", "source": "magic"})
