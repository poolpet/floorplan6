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
