"""
Eksport wygenerowanego rzutu do ArchiCAD jako strefy (zones).
"""
from __future__ import annotations

from typing import Optional

from core.models import FloorPlan, Room
from bridge.tapir_connection import TapirConnection


def export_plan_to_archicad(
    plan: FloorPlan,
    tapir: Optional[TapirConnection] = None,
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[str]:
    """Wyeksportuj rzut jako strefy do ArchiCAD.

    Args:
        plan: Wygenerowany rzut.
        tapir: Połączenie Tapir (opcjonalne).
        offset: Przesunięcie (x, y) w metrach — pozycja obrysu w ArchiCAD.

    Returns:
        Lista GUID-ów utworzonych stref.
    """
    if tapir is None:
        tapir = TapirConnection()
        tapir.connect()

    ox, oy = offset
    zones_data = []
    for i, room in enumerate(plan.rooms):
        if room.polygon is None:
            continue

        # Współrzędne polygonu pokoju (obsługa MultiPolygon) + offset
        geom = room.polygon
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        coords = list(geom.exterior.coords)
        poly_coords = [{"x": round(x + ox, 4), "y": round(y + oy, 4)} for x, y in coords[:-1]]

        zones_data.append({
            "name": room.spec.nazwa,
            "numberStr": str(i + 1),
            "geometry": {
                "polygonCoordinates": poly_coords,
            },
        })

    if not zones_data:
        raise ValueError("Brak pokoi z geometrią do wyeksportowania")

    guids = tapir.create_zones(zones_data)
    return guids
