"""Smoke: render_two_storey runs (no CP-SAT) and writes a PNG. Guards against crashes."""
import matplotlib
matplotlib.use("Agg")

from shapely.geometry import Polygon

from core.house_layout import TwoStoreyLayout
from core.models import Room, RoomSpec, Strefa
from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey


def _room(room_id, strefa, w, h, x=0.0, y=0.0):
    spec = RoomSpec(id=room_id, nazwa=room_id, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def test_render_two_storey_writes_png(tmp_path):
    parter = [
        _room("salon", Strefa.DZIENNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
        _room("kuchnia", Strefa.DZIENNA, 6.5, 2.0, 0.0, 3.0),
    ]
    pietro = [
        _room("sypialnia_1", Strefa.NOCNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
        _room("lazienka", Strefa.USLUGOWA, 6.5, 2.0, 0.0, 3.0),
    ]
    layout = TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                             stair_core=(4.0, 0.0, 2.5, 3.0), boundary=None)

    out = tmp_path / "house.png"
    fig = render_two_storey(
        layout,
        parter_furniture=place_furniture(parter),
        pietro_furniture=place_furniture(pietro),
        save_path=out, show=False,
    )
    assert len(fig.axes) >= 2
    assert out.exists() and out.stat().st_size > 0
