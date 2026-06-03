"""Miękka preferencja rozmieszczenia (Dawid 2026-06-03): kotłownia + garderoba lądują
przy ścianie ZEWNĘTRZNEJ gdy obrys pozwala (kotłownia — dopływ świeżego powietrza;
garderoba — okno). NIE obligatoryjne — testujemy na PRZESTRONNYCH obrysach gdzie ściana
jest dostępna, więc miękka nagroda powinna niezawodnie wygrać. Hol BEZ wymogu ściany."""
import pytest
from shapely.geometry import Polygon

from core.house_layout import generate_house


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


def _at_ext_wall(room, W, H, tol=0.05):
    b = room.polygon.bounds
    return (abs(b[0]) < tol or abs(b[2] - W) < tol or
            abs(b[1]) < tol or abs(b[3] - H) < tol)


def test_single_storey_kotlownia_garderoba_external_when_roomy():
    W, H = 10.0, 10.0  # 100 m² — zestaw zawiera kotłownię I garderobę, ściany jest dużo
    lay = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), (W / 2, 0.0),
                         num_storeys=1, time_limit_s=30)
    assert lay.ok, lay.message
    kot = _room(lay.parter_rooms, "kotlownia")
    gard = _room(lay.parter_rooms, "garderoba")
    assert kot is not None and gard is not None, "100 m² parterowiec ma kotłownię i garderobę"
    assert _at_ext_wall(kot, W, H), f"kotłownia w środku: {kot.polygon.bounds}"
    assert _at_ext_wall(gard, W, H), f"garderoba w środku: {gard.polygon.bounds}"


def test_two_storey_kotlownia_parter_garderoba_pietro_external():
    W, H = 11.0, 9.0
    lay = generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), (W / 2, 0.0),
                         num_storeys=2, time_limit_s=45)
    assert lay.ok, lay.message
    kot = _room(lay.parter_rooms, "kotlownia")    # parter
    gard = _room(lay.pietro_rooms, "garderoba")   # piętro
    assert _at_ext_wall(kot, W, H), f"kotłownia (parter) w środku: {kot.polygon.bounds}"
    assert _at_ext_wall(gard, W, H), f"garderoba (piętro) w środku: {gard.polygon.bounds}"
