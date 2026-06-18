"""Tryb architektoniczny renderera (#1-4): osie off, białe wnętrza, bez legendy, schody czarne."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from shapely.geometry import box, Polygon

from core.models import Room, RoomSpec, Strefa
from viz.plan_renderer import _draw_room, STREFA_COLORS

ZONE_RGB = {tuple(round(v, 3) for v in mcolors.to_rgb(c)) for c in STREFA_COLORS.values()}


def _room(room_id, strefa, w, h, x=0.0, y=0.0):
    spec = RoomSpec(id=room_id, nazwa=room_id, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _fill_rgbs(ax):
    return [tuple(round(v, 3) for v in p.get_facecolor()[:3])
            for p in ax.patches if isinstance(p, mpatches.Polygon)]


def test_draw_room_architectural_is_white_not_zone_color():
    fig, ax = plt.subplots()
    _draw_room(ax, _room("salon", Strefa.DZIENNA, 4, 3), architectural=True)
    rgbs = _fill_rgbs(ax)
    assert (1.0, 1.0, 1.0) in rgbs, f"brak białego wypełnienia: {rgbs}"
    assert not (ZONE_RGB & set(rgbs)), f"kolor strefy w trybie arch: {rgbs}"
    plt.close(fig)


def test_draw_room_default_keeps_zone_color():
    fig, ax = plt.subplots()
    _draw_room(ax, _room("salon", Strefa.DZIENNA, 4, 3), architectural=False)
    assert ZONE_RGB & set(_fill_rgbs(ax)), "default musi mieć kolor strefy"
    plt.close(fig)


# --- Task 2: ścieżka domu 2-kond. (render_two_storey) ---
from core.house_layout import TwoStoreyLayout
from core.furniture import place_furniture
from viz.plan_renderer import render_two_storey


def _house_layout():
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
    return TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                           stair_core=(4.0, 0.0, 2.5, 3.0), boundary=None)


def test_two_storey_architectural_axes_off_no_legend_white(tmp_path):
    fig = render_two_storey(_house_layout(), architectural=True,
                            save_path=tmp_path / "arch.png", show=False)
    for ax in fig.axes:
        assert ax.get_legend() is None, "tryb arch: brak legendy"
        assert ax.axison is False, "tryb arch: osie wyłączone"
        assert not (ZONE_RGB & set(_fill_rgbs(ax))), "tryb arch: brak kolorów stref"
    plt.close(fig)


def test_two_storey_default_unchanged(tmp_path):
    fig = render_two_storey(_house_layout(), save_path=tmp_path / "color.png", show=False)
    ax = fig.axes[0]
    assert ax.get_legend() is not None, "default: legenda obecna"
    assert ax.axison is True, "default: osie włączone"
    assert ZONE_RGB & set(_fill_rgbs(ax)), "default: kolory stref obecne"
    plt.close(fig)
