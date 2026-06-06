"""Kontrakt JSON rzutu (bundle-prep) — czysty, AC-agnostyczny core → {rooms,walls,doors,furniture}."""
import json

from shapely.geometry import Polygon, box

from core.models import Room, RoomSpec, Strefa, Template, AdjacencyRule
from core.boundary_analyzer import analyze_boundary
from core.furniture import furnish_rooms


def _room(rid, strefa, x0, y0, x1, y1, wymaga_okna=False):
    spec = RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=wymaga_okna, priorytet_fasady=None)
    r = Room(spec=spec, polygon=box(x0, y0, x1, y1)); r.update_metrics()
    return r


def _scenario():
    # salon | hub | sypialnia w rzędzie (10x4); hub styka się z oboma → 2 ścianki + 2 drzwi
    salon = _room("salon", Strefa.DZIENNA, 0, 0, 4, 4, wymaga_okna=True)
    hub = _room("hub", Strefa.KOMUNIKACJA, 4, 0, 6, 4)
    syp = _room("sypialnia_1", Strefa.NOCNA, 6, 0, 10, 4, wymaga_okna=True)
    rooms = [salon, hub, syp]
    boundary = analyze_boundary(Polygon([(0, 0), (10, 0), (10, 4), (0, 4)]), entry_point=(5, 0))
    template = Template(
        id="t", nazwa="T", typ_mieszkania="M3",
        pokoje=[r.spec for r in rooms],
        sasiedztwo=[AdjacencyRule("salon", "hub", "door"), AdjacencyRule("sypialnia_1", "hub", "door")],
    )
    return rooms, boundary, template


def test_plan_contract_shape_and_json():
    from core.plan_contract import plan_to_contract
    rooms, boundary, template = _scenario()
    fr = furnish_rooms(rooms, boundary)
    c = plan_to_contract(rooms, boundary, fr, storey="parter", template=template)
    assert set(c) >= {"meta", "rooms", "walls", "doors", "furniture", "warnings"}
    assert c["meta"]["storey"] == "parter"
    assert {r["id"] for r in c["rooms"]} == {"salon", "hub", "sypialnia_1"}
    assert all({"id", "name", "strefa", "area", "polygon"} <= set(r) for r in c["rooms"])
    assert c["furniture"], "brak mebli w kontrakcie"
    assert all({"type", "room_id", "polygon"} <= set(f) for f in c["furniture"])
    # w pełni JSON-serializowalny (zero Shapely/enum/np w wartościach)
    s = json.dumps(c)
    assert isinstance(s, str) and len(s) > 100


def test_plan_contract_walls_and_doors():
    from core.plan_contract import plan_to_contract
    rooms, boundary, template = _scenario()
    fr = furnish_rooms(rooms, boundary)
    c = plan_to_contract(rooms, boundary, fr, storey="parter", template=template)
    wall_pairs = {frozenset((w["room_a"], w["room_b"])) for w in c["walls"]}
    assert frozenset(("salon", "hub")) in wall_pairs
    assert frozenset(("hub", "sypialnia_1")) in wall_pairs
    assert len(c["doors"]) == 2, c["doors"]
    for d in c["doors"]:
        assert d["type"] in ("door", "opening")
        assert len(d["center"]) == 2
        assert d["width"] > 0


def test_plan_contract_without_template_no_doors():
    from core.plan_contract import plan_to_contract
    rooms, boundary, _ = _scenario()
    fr = furnish_rooms(rooms, boundary)
    c = plan_to_contract(rooms, boundary, fr, storey="parter", template=None)
    assert c["doors"] == []
    assert c["walls"], "ściany działowe powinny być nawet bez template"
    assert c["furniture"]


def test_house_to_contract_on_generated_house():
    # integracja: realny wygenerowany dom → pełny kontrakt, JSON-serializowalny
    from core.house_layout import generate_house
    from core.plan_contract import house_to_contract
    lay = generate_house(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), (5.0, 0.0),
                         num_storeys=1, time_limit_s=30)
    assert lay.ok, lay.message
    fr = furnish_rooms(lay.parter_rooms, boundary=lay.boundary)
    c = house_to_contract(lay, parter_furnish=fr)
    json.dumps(c)   # nie może rzucić (zero Shapely/enum w wartościach)
    parter = c["parter"]
    assert len(parter["rooms"]) == len(lay.parter_rooms)
    assert parter["walls"], "dom powinien mieć ścianki działowe"
    assert parter["furniture"]
    assert isinstance(parter["doors"], list) and parter["doors"], "brak drzwi z template'u domu"
