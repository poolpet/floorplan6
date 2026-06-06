"""GUI-free tests for viz/house_preview.py (Plan 3 — house mode orchestration)."""
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from shapely.geometry import Polygon

from core.house_layout import TwoStoreyLayout
from core.models import Room, RoomSpec, Strefa
from viz.house_preview import furnish_layout, house_details_text, render_house_figure


def _room(room_id, nazwa, strefa, w, h, x=0.0, y=0.0):
    spec = RoomSpec(id=room_id, nazwa=nazwa, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
    r.update_metrics()
    return r


def _layout():
    parter = [
        _room("salon", "Salon", Strefa.DZIENNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", "Hol", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
    ]
    pietro = [
        _room("sypialnia_1", "Sypialnia 1", Strefa.NOCNA, 4.0, 3.0, 0.0, 0.0),
        _room("hub", "Hol", Strefa.KOMUNIKACJA, 2.5, 3.0, 4.0, 0.0),
    ]
    return TwoStoreyLayout(ok=True, parter_rooms=parter, pietro_rooms=pietro,
                           stair_core=(4.0, 0.0, 2.5, 3.0), boundary=None)


def test_furnish_layout_toggle():
    layout = _layout()
    pf_on, pif_on = furnish_layout(layout, with_furniture=True)
    pf_off, pif_off = furnish_layout(layout, with_furniture=False)
    assert len(pf_on) > 0          # parter: salon dostaje meble
    assert len(pif_on) > 0         # piętro: sypialnia dostaje meble
    assert pf_off == [] and pif_off == []


def test_furnish_layout_forwards_boundary(monkeypatch):
    # regresja #18: furnish_layout MUSI przekazać layout.boundary do place_furniture,
    # inaczej meble nie są window-aware w realnym produkcie (phase 4 omijane).
    import viz.house_preview as hp
    captured = []

    def fake_place(rooms, boundary=None):
        captured.append(boundary)
        return []

    monkeypatch.setattr(hp, "place_furniture", fake_place)
    layout = _layout()
    sentinel = object()
    layout.boundary = sentinel
    hp.furnish_layout(layout, with_furniture=True)
    assert captured == [sentinel, sentinel], "boundary nie przekazany do place_furniture (window-blind)"


def test_house_details_text_has_both_storeys():
    text = house_details_text(_layout())
    assert "PARTER" in text and "PIĘTRO" in text
    assert "Salon" in text and "Sypialnia 1" in text


def test_render_house_figure_two_panels():
    fig = render_house_figure(_layout(), with_furniture=True, show=False)
    assert len(fig.axes) >= 2
    plt.close(fig)


def test_render_house_figure_writes_png(tmp_path):
    out = tmp_path / "house.png"
    fig = render_house_figure(_layout(), with_furniture=False, save_path=out, show=False)
    assert out.exists() and out.stat().st_size > 0
    plt.close(fig)


def test_house_details_text_uses_boundary_area():
    from core.boundary_analyzer import analyze_boundary
    layout = _layout()
    layout.boundary = analyze_boundary(Polygon([(0, 0), (8, 0), (8, 10), (0, 10)]), (4.0, 0.0))
    text = house_details_text(layout)
    assert "80.0 m²" in text
