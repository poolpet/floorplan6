"""Dom → AC write-back: per-kondygnację FloorPlan z właściwym szablonem (reuse writera)."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import TwoStoreyLayout
from core.models import Room, RoomSpec, Strefa
import bridge.house_writer as hw


def _room(rid, strefa, w=3.0, h=3.0, x=0.0, y=0.0):
    spec = RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _two_storey():
    return TwoStoreyLayout(
        ok=True,
        parter_rooms=[_room("salon", Strefa.DZIENNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        pietro_rooms=[_room("sypialnia_1", Strefa.NOCNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        stair_core=(3.0, 0.0, 2.0, 3.0), boundary=None)


def _single_storey():
    return TwoStoreyLayout(
        ok=True,
        parter_rooms=[_room("salon", Strefa.DZIENNA), _room("hub", Strefa.KOMUNIKACJA, x=3)],
        pietro_rooms=[], stair_core=(0.0, 0.0, 0.0, 0.0), boundary=None)


@pytest.fixture
def spy(monkeypatch):
    """Podmień writer mieszkań na szpiega — izoluje logikę house_writer od Tapira/AC."""
    captured = {}

    def fake(plan, **kw):
        captured["plan"] = plan
        captured["kw"] = kw
        return {"zones": ["z"], "walls": [], "doors": [], "labels": [], "windows": []}

    monkeypatch.setattr(hw, "export_plan_to_archicad", fake)
    return captured


def test_parter_uses_house_parter_template_and_rooms(spy):
    layout = _two_storey()
    res = hw.export_house_to_archicad(layout, storey="parter")
    assert spy["plan"].template.id == "house_parter"
    assert spy["plan"].rooms is layout.parter_rooms
    assert spy["kw"]["include_furniture"] is False
    assert spy["kw"]["apartment_id"] == "DOM-PARTER"
    assert res["storey"] == "parter"


def test_poddasze_uses_house_pietro_template_and_rooms(spy):
    layout = _two_storey()
    hw.export_house_to_archicad(layout, storey="poddasze")
    assert spy["plan"].template.id == "house_pietro"
    assert spy["plan"].rooms is layout.pietro_rooms
    assert spy["kw"]["apartment_id"] == "DOM-PODDASZE"


def test_single_storey_uses_house_single_storey_template(spy):
    hw.export_house_to_archicad(_single_storey(), storey="parter")
    assert spy["plan"].template.id == "house_single_storey"


def test_poddasze_on_parterowiec_raises(spy):
    with pytest.raises(ValueError):
        hw.export_house_to_archicad(_single_storey(), storey="poddasze")


def test_unknown_storey_raises(spy):
    with pytest.raises(ValueError):
        hw.export_house_to_archicad(_two_storey(), storey="garaz")
