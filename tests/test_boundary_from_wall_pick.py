"""
Testy auto-detect obrysu z zaznaczonej ściany (read_boundary_from_wall_pick).

Mock TapirConnection — symuluje selekcję 1 ściany w AC + obie strony
auto-zone (jedna daje mieszkanie, druga albo failuje albo całe piętro).

Sprawdza:
  1. Happy path: 1 sciana zaznaczona, jedna strona daje polygon 5x5 → wygrywa
  2. Obie strony dają polygony — wygrywa mniejszy (mieszkanie, nie piętro)
  3. Brak zaznaczenia → ValueError
  4. Zaznaczono nie-Wall (np. Door) → ValueError
  5. Ściana o zerowej długości → ValueError
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bridge.boundary_reader import read_boundary_from_wall_pick


def _make_tapir_wall_selected(
    wall_beg=(0.0, 0.0),
    wall_end=(5.0, 0.0),
    wall_type="Wall",
    polygon_per_side: dict | None = None,
):
    """Tapir mock z 1 zaznaczoną ścianą + konfigurowalne polygony per strona.

    polygon_per_side: {+1: [pts] | None, -1: [pts] | None}
        Lista punktów → side da polygon o tej geometrii.
        None → side rzuci wyjątek (AC nie znalazł obrysu).
    """
    polygon_per_side = polygon_per_side or {}
    tapir = MagicMock()
    wall_guid = "wall-guid-123"

    tapir.get_selected_elements.return_value = [
        {"elementId": {"guid": wall_guid}}
    ]
    tapir.get_element_details.return_value = [{
        "type": wall_type,
        "details": {
            "begCoordinate": {"x": wall_beg[0], "y": wall_beg[1]},
            "endCoordinate": {"x": wall_end[0], "y": wall_end[1]},
        },
    }]

    # Symulujemy 2 wywołania create_temp_zone_at_point (po jednym na stronę)
    side_results = []
    side_polygons = []
    for sign in (+1, -1):
        pts = polygon_per_side.get(sign)
        if pts is None:
            side_results.append(None)        # AC nie znalazł obrysu
            side_polygons.append([])
        else:
            side_results.append(f"tmp-zone-{sign}")
            side_polygons.append(pts)

    tapir.create_temp_zone_at_point.side_effect = side_results
    tapir.get_zone_polygon.side_effect = side_polygons
    tapir.delete_elements.return_value = 1

    # Brak drzwi w projekcie - heurystyka entry
    tapir.get_elements_by_type.return_value = []

    return tapir


def test_happy_path_one_side_yields_apartment():
    """Strona +1 daje pokój 5x5 (25m²), strona -1 fail → wygrywa +1."""
    pts = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    tapir = _make_tapir_wall_selected(polygon_per_side={+1: pts, -1: None})

    polygon, entry, wall_types = read_boundary_from_wall_pick(tapir=tapir)

    assert polygon.area == pytest.approx(25.0, abs=0.01)
    assert polygon.is_valid
    assert len(wall_types) == 4


def test_two_sides_smaller_wins():
    """Strona +1: pokój 5x5 (25m²); strona -1: całe piętro 30x30 (900m²).
    Wygrywa mniejszy = mieszkanie."""
    small = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    big = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]
    tapir = _make_tapir_wall_selected(polygon_per_side={+1: small, -1: big})

    polygon, entry, wall_types = read_boundary_from_wall_pick(tapir=tapir)

    # Powinien wybrać mieszkanie (mniejsze)
    assert polygon.area == pytest.approx(25.0, abs=0.01)


def test_no_selection_raises():
    tapir = MagicMock()
    tapir.get_selected_elements.return_value = []
    with pytest.raises(ValueError, match="Brak zaznaczonych"):
        read_boundary_from_wall_pick(tapir=tapir)


def test_non_wall_selected_raises():
    """Zaznaczono drzwi (Door) zamiast ściany → ValueError z listą typów."""
    tapir = MagicMock()
    tapir.get_selected_elements.return_value = [{"elementId": {"guid": "d1"}}]
    tapir.get_element_details.return_value = [{"type": "Door", "details": {}}]
    with pytest.raises(ValueError, match="nie zawierają ściany"):
        read_boundary_from_wall_pick(tapir=tapir)


def test_zero_length_wall_raises():
    """begC == endC → ściana zero-length → ValueError."""
    tapir = _make_tapir_wall_selected(
        wall_beg=(1.0, 1.0), wall_end=(1.0, 1.0),
        polygon_per_side={+1: None, -1: None},
    )
    with pytest.raises(ValueError, match="zerową długość"):
        read_boundary_from_wall_pick(tapir=tapir)


def test_both_sides_out_of_range_raises():
    """Obie strony dają polygon poza zakresem [8, 500] m² → ValueError."""
    tiny = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]   # 1m² - za mały
    huge = [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)]  # 2500m² - za duży
    tapir = _make_tapir_wall_selected(polygon_per_side={+1: tiny, -1: huge})

    with pytest.raises(ValueError, match="żadnej stronie"):
        read_boundary_from_wall_pick(tapir=tapir)
