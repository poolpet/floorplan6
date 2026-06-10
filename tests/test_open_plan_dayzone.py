"""Faza 1 — open-plan day-zone (Approach B): strefa dzienna jako otwarta grupa
funkcjonalna (salon+kuchnia), łączny cap, salon na fasadzie ogrodowej (przeciwnej
do wejścia), ciągłość grupy. Grunt: rzuty PROJ-BUD/Łącko + ARCHON.
"""
from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.models import Strefa


def _gen(W, H, entry, t=45.0):
    return generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), entry,
                          num_storeys=2, time_limit_s=t)


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


def _shared_edge_len(a, b) -> float:
    return a.polygon.boundary.intersection(b.polygon.boundary).length


# Obrysy ≥ ~76 m²: knee-wall (S26) solvuje piętro na PASIE poddasza (0.6 krótszej
# osi), więc 10×7 (pas 42 m²) jest za małe na stały program piętra (suma minów 40.5·margines).

def test_salon_on_garden_facade_opposite_south_entry():
    """Wejście S → salon (strefa dzienna) dotyka ściany N (fasada ogrodowa)."""
    layout = _gen(11.0, 8.0, (5.5, 0.0))
    assert layout.ok, layout.message
    salon = _room(layout.parter_rooms, "salon")
    assert abs(salon.polygon.bounds[3] - 8.0) < 0.05  # górna krawędź = N (y=H)


def test_salon_on_garden_facade_opposite_west_entry():
    """Wejście W → salon dotyka ściany E (fasada ogrodowa)."""
    layout = _gen(11.0, 8.0, (0.0, 4.0))
    assert layout.ok, layout.message
    salon = _room(layout.parter_rooms, "salon")
    assert abs(salon.polygon.bounds[2] - 11.0) < 0.05  # prawa krawędź = E (x=W)


def test_day_zone_contiguous_open_plan():
    """Strefa dzienna ciągła: salon i kuchnia dzielą krawędź ≥0.9 m (jedna otwarta
    przestrzeń, może ułożyć się w L lub prostokąt)."""
    layout = _gen(11.0, 8.0, (5.5, 0.0))
    assert layout.ok, layout.message
    salon, kuchnia = _room(layout.parter_rooms, "salon"), _room(layout.parter_rooms, "kuchnia")
    assert salon.spec.strefa == Strefa.DZIENNA and kuchnia.spec.strefa == Strefa.DZIENNA
    assert _shared_edge_len(salon, kuchnia) >= 0.9 - 1e-6
