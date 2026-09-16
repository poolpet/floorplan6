import pytest
from shapely.geometry import Polygon


def _fake_plan():
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan
    from core.template_selector import load_all_templates

    tpl = next(t for t in load_all_templates() if t.id == "M2_standard")
    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    return FloorPlan(boundary=analyze_boundary(poly, (4.0, 0.0)), template=tpl, rooms=[], score=0.9)


def test_apartment_request_returns_contracts(monkeypatch):
    import service.solve_adapter as sa

    fake_plan = _fake_plan()
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
    assert out["variants"][0]["index"] == 0
    assert out["variants"][0]["validation_errors"] == []
    c = out["variants"][0]["contract"]
    assert "rooms" in c and "walls" in c
    assert out["boundary"]["area"] == 48.0 and out["boundary"]["auto_type"] == "M2"
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
    assert out["variants"][0]["contract"]["_src"] == "LAYOUT"
    assert called["kw"]["num_storeys"] == 2


@pytest.mark.parametrize("bad,match", [
    # brak polygon
    ({"mode": "apartment", "entry": [0, 0], "mtype": "M2"},
     "at least 3 points"),
    # <3 pkt
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0]], "entry": [0, 0], "mtype": "M2"},
     "at least 3 points"),
    # zły mode
    ({"mode": "xyz", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0]},
     "must be 'apartment' or 'house'"),
    # zły typ mieszkania
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0], "mtype": "M9"},
     "Apartment type"),
    # punkt obrysu nie jest liczbą
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0], ["a", 1]], "entry": [0, 0], "mtype": "M2"},
     "pairs of numbers"),
    # obrys z samoprzecięciem
    ({"mode": "apartment", "polygon": [[0, 0], [2, 0], [0, 2], [2, 2]], "entry": [0, 0], "mtype": "M2"},
     "The outline is invalid"),
    # entry nie jest parą
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [0, 0, 0], "mtype": "M2"},
     "must be a pair"),
    # entry z None w środku (JSON null)
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": [None, 0], "mtype": "M2"},
     "Entry point 'entry' must be a number"),
    # entry nieliczbowe
    ({"mode": "apartment", "polygon": [[0, 0], [1, 0], [1, 1]], "entry": ["a", 0], "mtype": "M2"},
     "Entry point 'entry' must be a number"),
    # num_storeys nie jest liczbą
    ({"mode": "house", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]], "entry": [5, 0],
      "num_storeys": "abc"},
     "'num_storeys' must be a whole number"),
    # max_variants nie jest liczbą
    ({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0],
      "mtype": "M2", "max_variants": "duzo"},
     "'max_variants' must be a whole number"),
    # min_score nie jest liczbą
    ({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]], "entry": [4, 0],
      "mtype": "M2", "min_score": "x"},
     "'min_score' must be a number"),
])
def test_invalid_request_raises_value_error(bad, match):
    import service.solve_adapter as sa
    with pytest.raises(ValueError, match=match):
        sa.solve_request(bad)


def test_null_optional_fields_fall_back_to_defaults(monkeypatch):
    """JSON null w polach opcjonalnych = 'nie podano' → default, nie błąd."""
    import service.solve_adapter as sa

    fake_plan = _fake_plan()
    seen = {}

    def fake_generate(polygon, entry_point, mtype, max_variants, progress_callback=None, **kw):
        seen.update(max_variants=max_variants, kw=kw)
        return [fake_plan]

    monkeypatch.setattr(sa, "generate_variants", fake_generate)
    out = sa.solve_request({"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]],
                            "entry": [4, 0], "mtype": "M2",
                            "max_variants": None, "min_score": None})
    assert len(out["variants"]) == 1
    assert seen["max_variants"] == 5
    assert seen["kw"]["min_score"] == 0.0


def test_null_num_storeys_falls_back_to_default(monkeypatch):
    import service.solve_adapter as sa
    called = {}

    def fake_house(p, e, **kw):
        called.setdefault("kw", kw)
        return "LAYOUT"

    monkeypatch.setattr(sa, "generate_house", fake_house)
    monkeypatch.setattr(sa, "house_to_contract", lambda layout: {"_src": layout})
    sa.solve_request({"mode": "house", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]],
                      "entry": [5, 0], "num_storeys": None})
    assert called["kw"]["num_storeys"] == 2
