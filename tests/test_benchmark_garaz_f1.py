"""B1: garaz liczony w F1 (przynależność), ale NIE w MAPE (pole niepewne)."""
from notebooks.reference_benchmark import _ref_f1_types, _storey_rooms


def _storey(rooms):
    return {"rooms": [{"mapped_id": t, "name_pl": t, "area_m2": a} for t, a in rooms]}


def test_ref_f1_types_includes_garaz():
    s = _storey([("salon", 30.0), ("garaz", 18.0), ("lazienka", 5.0)])
    types = _ref_f1_types(s)
    assert "garaz" in types
    assert "salon" in types and "lazienka" in types


def test_ref_f1_types_excludes_schody_taras_other():
    s = _storey([("salon", 30.0), ("schody", 6.0), ("taras", 12.0), ("other", 4.0)])
    assert _ref_f1_types(s) == ["salon"]


def test_storey_rooms_still_excludes_garaz_for_mape():
    # MAPE path NIEzmieniona — garaz dalej wykluczony z _storey_rooms
    s = _storey([("salon", 30.0), ("garaz", 18.0)])
    types = [t for t, _ in _storey_rooms(s)]
    assert "garaz" not in types
    assert "salon" in types
