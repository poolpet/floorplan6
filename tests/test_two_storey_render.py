"""Smoke: render_two_storey runs (no CP-SAT) and writes a PNG. Guards against crashes."""
import matplotlib
matplotlib.use("Agg")

from shapely.geometry import Polygon, Point, box

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


def test_label_anchor_avoids_furniture():
    # MVP: etykieta nazwy pokoju nie może lądować na meblu (łóżko zakrywa centroid).
    from viz.plan_renderer import _label_anchor
    poly = box(0.0, 0.0, 4.0, 4.0)
    # bez mebli → centroid
    cx, cy = _label_anchor(poly, [])
    assert abs(cx - poly.centroid.x) < 1e-9 and abs(cy - poly.centroid.y) < 1e-9
    # łóżko zakrywa centroid (2,2) → kotwica etykiety poza meblem
    bed = box(0.5, 0.5, 3.5, 3.5)
    ax_, ay_ = _label_anchor(poly, [bed])
    assert poly.buffer(-1e-6).contains(Point(ax_, ay_)), "kotwica poza pokojem"
    assert not bed.contains(Point(ax_, ay_)), f"etykieta na meblu: {(ax_, ay_)}"


def test_render_floor_plan_draws_doors_and_windows(tmp_path):
    # MVP: rzut mieszkania rysuje drzwi (łuk swingu) i okna (niebieska linia na fasadzie).
    from matplotlib.patches import Arc
    from core.boundary_analyzer import analyze_boundary
    from core.models import FloorPlan, Room, RoomSpec, Strefa
    from core.furniture import furnish_rooms
    from viz.plan_renderer import render_floor_plan
    b = analyze_boundary(Polygon([(0, 0), (8, 0), (8, 4), (0, 4)]), entry_point=(4, 0))
    # sypialnia (NOCNA) → drzwi ze skrzydłem (łuk); strefa dzienna byłaby otwarciem bez łuku
    syp = Room(spec=RoomSpec(id="sypialnia_1", nazwa="Sypialnia", strefa=Strefa.NOCNA,
                             wymaga_okna=True, priorytet_fasady=1),
               polygon=box(0.0, 0.0, 4.0, 4.0)); syp.update_metrics()      # okno na W (x=0)
    hub = Room(spec=RoomSpec(id="hub", nazwa="Hol", strefa=Strefa.KOMUNIKACJA,
                             wymaga_okna=False, priorytet_fasady=None),
               polygon=box(4.0, 0.0, 8.0, 4.0)); hub.update_metrics()      # styk sypialnia↔hol → drzwi
    plan = FloorPlan(boundary=b, template=None, rooms=[syp, hub])
    fr = furnish_rooms([syp, hub], b)
    out = tmp_path / "apt.png"
    fig = render_floor_plan(plan, title="Mieszkanie", show=False, save_path=out, furniture=fr.furniture)
    ax = fig.axes[0]
    assert any(isinstance(p, Arc) for p in ax.patches), "brak symbolu drzwi (łuk swingu)"
    assert [ln for ln in ax.lines if ln.get_color() == "#1565C0"], "brak okna (niebieska linia)"
    assert out.exists() and out.stat().st_size > 0


def test_label_anchor_inside_non_convex_room():
    # review: U/L-pokój — kotwica etykiety MUSI być wewnątrz (centroid bywa w wycięciu, poza pokojem)
    from viz.plan_renderer import _label_anchor
    u = Polygon([(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)])  # U, centroid w wycięciu
    assert not u.contains(Point(u.centroid.x, u.centroid.y)), "fixture: centroid powinien być poza U"
    x, y = _label_anchor(u, [])
    assert u.contains(Point(x, y)), f"kotwica poza U-pokojem (bez mebli): {(x, y)}"
    f = box(0.0, 0.0, 1.0, 1.0)
    x2, y2 = _label_anchor(u, [f])
    assert u.contains(Point(x2, y2)) and not f.contains(Point(x2, y2)), f"kotwica poza pokojem/na meblu: {(x2, y2)}"


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
