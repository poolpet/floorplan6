import pytest
from shapely.geometry import Polygon


def test_apartment_request_returns_contracts(monkeypatch):
    import service.solve_adapter as sa
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan
    from core.template_selector import load_all_templates

    tpl = next(t for t in load_all_templates() if t.id == "M2_standard")
    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    fake_plan = FloorPlan(boundary=analyze_boundary(poly, (4.0, 0.0)), template=tpl, rooms=[], score=0.9)
    seen = {}

    def fake_generate(polygon, entry_point, mtype, max_variants, progress_callback=None, **kw):
        seen.update(mtype=mtype, max_variants=max_variants, kw=kw)
        if progress_callback:
            progress_callback(1, 1)
        return [fake_plan]

    monkeypatch.setattr(sa, "generate_variants", fake_generate)
    ticks = []
    out = sa.solve_request(
        {"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0],
         "mtype": "M2", "max_variants": 3},
        progress=lambda c, t: ticks.append((c, t)),
    )
    assert out["mode"] == "apartment"
    assert len(out["variants"]) == 1
    assert out["variants"][0]["score"] == 0.9
    assert "rooms" in out["variants"][0] and "walls" in out["variants"][0]
    assert seen["mtype"] == "M2" and seen["max_variants"] == 3
    assert ticks == [(1, 1)]


def test_house_request_returns_layout_contract(monkeypatch):
    import service.solve_adapter as sa
    called = {}

    def fake_house(p, e, **kw):
        called.setdefault("kw", kw)
        return "LAYOUT"

    monkeypatch.setattr(sa, "generate_house", fake_house)
    monkeypatch.setattr(sa, "house_to_contract", lambda layout: {"parter": {"rooms": []}, "_src": layout})
    out = sa.solve_request({"mode": "house", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]],
                            "entry": [5, 0], "num_storeys": 2})
    assert out["mode"] == "house"
    assert out["layout"]["_src"] == "LAYOUT"
    assert called["kw"]["num_storeys"] == 2


@pytest.mark.parametrize("bad", [
    {"mode": "apartment", "entry": [0, 0], "mtype": "M2"},                      # brak polygon
    {"mode": "apartment", "polygon": [[0, 0], [1, 0]], "entry": [0, 0], "mtype": "M2"},  # <3 pkt
    {"mode": "xyz", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0]},      # zły mode
    {"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0], "mtype": "M9"},
])
def test_invalid_request_raises_value_error(bad):
    import service.solve_adapter as sa
    with pytest.raises(ValueError):
        sa.solve_request(bad)
