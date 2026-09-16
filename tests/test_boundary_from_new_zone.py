"""
Testy auto-detect obrysu z natywnego Inner Edge w AC (read_boundary_from_new_zone).

Mock Tapir symuluje workflow:
  - user przed akcją: 2 istniejące Zone (A, B)
  - user w AC: Z + klik → AC tworzy Zone C
  - read_boundary_from_new_zone wykrywa C, czyta polygon, usuwa C

Sprawdza:
  1. Happy path: znajduje nowy Zone, polygon zwrócony, delete wywołany
  2. Brak nowej Zone → ValueError (user nic nie zrobił w AC)
  3. before_guids=None i istniejące Zone → bierze wszystkie jako "nowe"
  4. Cleanup nie udał się → polygon i tak zwrócony (best-effort)
  5. cleanup=False → Zone nie usuwana
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bridge.boundary_reader import read_boundary_from_new_zone


def _make_tapir(
    current_zone_guids: list[str],
    polygon_pts: list[tuple[float, float]] | None = None,
    delete_raises: bool = False,
):
    tapir = MagicMock()
    tapir.get_elements_by_type.return_value = [
        {"elementId": {"guid": g}} for g in current_zone_guids
    ]
    tapir.get_zone_polygon.return_value = polygon_pts or [
        (0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)
    ]
    if delete_raises:
        tapir.delete_elements.side_effect = RuntimeError("delete failed")
    else:
        tapir.delete_elements.return_value = 1
    # heurystyka drzwi - brak
    tapir.get_element_details.return_value = []
    return tapir


def test_happy_path_new_zone_detected_and_deleted():
    """Pre: {A,B}. Po user action: {A,B,C}. Wynik: polygon z C + delete(C)."""
    tapir = _make_tapir(current_zone_guids=["A", "B", "C"])

    polygon, entry, wall_types = read_boundary_from_new_zone(
        tapir, before_guids={"A", "B"}, cleanup=True,
    )

    assert polygon.area == pytest.approx(25.0, abs=0.01)
    assert polygon.is_valid

    # cleanup wywołany na "C"
    tapir.delete_elements.assert_called_once()
    deleted = tapir.delete_elements.call_args[0][0]
    assert deleted == ["C"]


def test_no_new_zone_raises():
    """Pre: {A,B}. Po user action: {A,B}. ValueError = user nic nie zrobił."""
    tapir = _make_tapir(current_zone_guids=["A", "B"])
    with pytest.raises(ValueError, match="No new Zone was detected"):
        read_boundary_from_new_zone(tapir, before_guids={"A", "B"})


def test_before_guids_none_takes_all():
    """Brak snapshotu → wszystkie aktualne Zone traktowane jako 'nowe'."""
    tapir = _make_tapir(current_zone_guids=["X"])
    polygon, entry, wall_types = read_boundary_from_new_zone(
        tapir, before_guids=None,
    )
    assert polygon.area == pytest.approx(25.0, abs=0.01)


def test_cleanup_failure_does_not_block_import():
    """Delete padnie ale polygon i tak zwrócony."""
    tapir = _make_tapir(
        current_zone_guids=["A", "C"],
        delete_raises=True,
    )
    polygon, entry, wall_types = read_boundary_from_new_zone(
        tapir, before_guids={"A"}, cleanup=True,
    )
    assert polygon.area == pytest.approx(25.0, abs=0.01)
    tapir.delete_elements.assert_called_once()


def test_cleanup_false_skips_delete():
    """cleanup=False → Zone zostaje w AC."""
    tapir = _make_tapir(current_zone_guids=["A", "C"])
    read_boundary_from_new_zone(
        tapir, before_guids={"A"}, cleanup=False,
    )
    tapir.delete_elements.assert_not_called()


def test_polygon_too_few_points_raises():
    """Zone z <3 punkty → ValueError, ale cleanup nadal wykonany."""
    tapir = _make_tapir(
        current_zone_guids=["A", "C"],
        polygon_pts=[(0.0, 0.0), (5.0, 0.0)],  # tylko 2 punkty
    )
    with pytest.raises(ValueError, match="fewer than 3 polygon points"):
        read_boundary_from_new_zone(tapir, before_guids={"A"})
    # cleanup MUSI być wywołany nawet jak read padnie
    tapir.delete_elements.assert_called_once()
