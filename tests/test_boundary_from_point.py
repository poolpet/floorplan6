"""
Testy auto-detect obrysu z klika (read_boundary_from_point).

Mock TapirConnection — symuluje:
  - create_temp_zone_at_point → temp_guid
  - get_zone_polygon → wierzchołki kwadratu 5×5
  - delete_elements → cleanup
  - get_elements_by_type/get_element_details → puste (brak drzwi)

Sprawdza:
  1. Happy path: klik wewnątrz → polygon zwrócony, temp Zone usunięta
  2. AC nie znalazł obrysu (None GUID) → ValueError
  3. Polygon <3 punktów → ValueError + cleanup nadal robiony
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from shapely.geometry import Polygon

from bridge.boundary_reader import read_boundary_from_point


def _make_fake_tapir(polygon_points: list[tuple[float, float]] | None,
                    temp_guid: str | None = "fake-zone-guid"):
    """Buduje MagicMock Tapir z konfigurowalnymi response."""
    tapir = MagicMock()
    tapir.create_temp_zone_at_point.return_value = temp_guid
    tapir.get_zone_polygon.return_value = polygon_points or []
    tapir.delete_elements.return_value = 1
    # auto-detect drzwi -> brak, fallback do heurystyki
    tapir.get_elements_by_type.return_value = []
    tapir.get_element_details.return_value = []
    return tapir


def test_happy_path_rectangle():
    """Klik w (2.5, 2.5) → AC zwraca kwadrat 5×5 → poprawny polygon + cleanup."""
    pts = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    tapir = _make_fake_tapir(pts)

    polygon, entry, wall_types = read_boundary_from_point(2.5, 2.5, tapir=tapir)

    # Polygon ma 4 wierzchołki
    coords = list(polygon.exterior.coords)
    assert len(coords) - 1 == 4
    # Polygon poprawny
    assert polygon.is_valid
    assert polygon.area == pytest.approx(25.0, abs=0.01)
    # Wall types — fallback heurystyka (najkrótsza krawędź = INTERNAL)
    assert len(wall_types) == 4
    # Cleanup faktycznie zrobiony
    tapir.create_temp_zone_at_point.assert_called_once_with(2.5, 2.5)
    tapir.delete_elements.assert_called_once_with(["fake-zone-guid"])


def test_ac_did_not_find_outline_raises():
    """AC zwrócił None GUID (brak zamkniętego obrysu) → ValueError."""
    tapir = _make_fake_tapir(polygon_points=None, temp_guid=None)

    with pytest.raises(ValueError, match="nie znalazł zamkniętego obrysu"):
        read_boundary_from_point(1.0, 1.0, tapir=tapir)

    # Nie ma temp_guid, więc delete nie powinno być wołane
    tapir.delete_elements.assert_not_called()


def test_polygon_too_small_raises_with_cleanup():
    """Polygon ma <3 punkty (corrupt) → ValueError, ale cleanup nadal."""
    tapir = _make_fake_tapir(polygon_points=[(0.0, 0.0), (1.0, 0.0)])

    with pytest.raises(ValueError, match="<3 punkt"):
        read_boundary_from_point(0.5, 0.5, tapir=tapir)

    # Cleanup mimo błędu
    tapir.delete_elements.assert_called_once()


def test_cleanup_on_unexpected_exception():
    """Jeśli get_zone_polygon rzuci nieoczekiwany błąd, cleanup nadal idzie."""
    tapir = _make_fake_tapir(polygon_points=[(0.0, 0.0), (5, 0), (5, 5), (0, 5)])
    tapir.get_zone_polygon.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        read_boundary_from_point(2.5, 2.5, tapir=tapir)

    tapir.delete_elements.assert_called_once_with(["fake-zone-guid"])


def test_l_shape_polygon():
    """L-shape (6 wierzchołków) — wykryć i zwrócić poprawny polygon."""
    pts = [
        (0.0, 0.0), (8.0, 0.0), (8.0, 4.0),
        (5.0, 4.0), (5.0, 7.0), (0.0, 7.0),
    ]
    tapir = _make_fake_tapir(pts)

    polygon, entry, wall_types = read_boundary_from_point(2.0, 2.0, tapir=tapir)

    assert polygon.is_valid
    # area = 8*4 + 5*3 = 32 + 15 = 47
    assert polygon.area == pytest.approx(47.0, abs=0.01)
    coords = list(polygon.exterior.coords)
    assert len(coords) - 1 == 6
