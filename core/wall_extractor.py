"""
Ekstrakcja ścian działowych z wygenerowanego rzutu.

Szuka wspólnych krawędzi między pokojami — to są ścianki działowe.
Krawędzie zewnętrzne (boundary mieszkania) pomijamy — są już narysowane
w ArchiCAD jako obrys.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, MultiLineString, Polygon

from core.models import FloorPlan

# Domyślne parametry ścianek działowych (typowy lokal mieszkalny PL)
DEFAULT_WALL_HEIGHT_M = 2.7
DEFAULT_WALL_THICKNESS_M = 0.10
DEFAULT_Z_OFFSET_M = 0.0

# Minimalna długość segmentu uznawanego za ścianę (krótsze = artefakt)
MIN_WALL_LENGTH_M = 0.30


@dataclass
class WallSegment:
    """Segment ściany działowej między dwoma pokojami."""
    p1: tuple[float, float]
    p2: tuple[float, float]
    height: float = DEFAULT_WALL_HEIGHT_M
    thickness: float = DEFAULT_WALL_THICKNESS_M
    z_offset: float = DEFAULT_Z_OFFSET_M
    # Diagnostyka — jakie pokoje są po obu stronach
    room_a: str = ""
    room_b: str = ""

    @property
    def length(self) -> float:
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        return (dx * dx + dy * dy) ** 0.5


def extract_internal_walls(
    plan: FloorPlan,
    height: float = DEFAULT_WALL_HEIGHT_M,
    thickness: float = DEFAULT_WALL_THICKNESS_M,
    min_length: float = MIN_WALL_LENGTH_M,
) -> list[WallSegment]:
    """Wyciągnij ścianki działowe z rzutu (wspólne krawędzie między pokojami).

    Args:
        plan: Wygenerowany FloorPlan z pokojami mającymi `polygon`.
        height: Wysokość ścian (m).
        thickness: Grubość ścian (m).
        min_length: Minimalna długość segmentu uznawanego za ścianę.

    Returns:
        Lista WallSegment — każda ściana raz (deduplikacja).
    """
    rooms = [r for r in plan.rooms if r.polygon is not None]
    walls: list[WallSegment] = []

    for i, room_a in enumerate(rooms):
        for room_b in rooms[i + 1:]:
            shared = _shared_edge(room_a.polygon, room_b.polygon)
            for line in shared:
                if line.length < min_length:
                    continue
                coords = list(line.coords)
                # Bierzemy końce LineString — w przypadku zaokrągleń shapely
                # może dorzucić pośrednie punkty, ale dla MVP jeden segment.
                p1 = (coords[0][0], coords[0][1])
                p2 = (coords[-1][0], coords[-1][1])
                walls.append(WallSegment(
                    p1=p1,
                    p2=p2,
                    height=height,
                    thickness=thickness,
                    room_a=room_a.spec.nazwa,
                    room_b=room_b.spec.nazwa,
                ))

    return walls


def _shared_edge(poly_a: Polygon, poly_b: Polygon) -> list[LineString]:
    """Wspólne odcinki granic dwóch polygonów.

    Zwraca tylko LineString-i (skip Points = same narożniki).
    """
    if poly_a is None or poly_b is None:
        return []

    intersection = poly_a.boundary.intersection(poly_b.boundary)
    if intersection.is_empty:
        return []

    out: list[LineString] = []
    if intersection.geom_type == "LineString":
        out.append(intersection)
    elif intersection.geom_type == "MultiLineString":
        for geom in intersection.geoms:
            out.append(geom)
    elif intersection.geom_type == "GeometryCollection":
        for geom in intersection.geoms:
            if geom.geom_type == "LineString":
                out.append(geom)
            elif geom.geom_type == "MultiLineString":
                for sub in geom.geoms:
                    out.append(sub)
    # Skip Point / MultiPoint - same narożniki, nie ściana
    return out


def walls_to_tapir_payload(walls: list[WallSegment]) -> list[dict]:
    """Konwertuje listę WallSegment do formatu Tapir CreateWalls.

    Wymagane pola (wg schema CreateWalls 1.4.0):
        begCoordinate, endCoordinate, zCoordinate, height, thickness
    """
    return [
        {
            "begCoordinate": {"x": round(w.p1[0], 6), "y": round(w.p1[1], 6)},
            "endCoordinate": {"x": round(w.p2[0], 6), "y": round(w.p2[1], 6)},
            "zCoordinate": w.z_offset,
            "height": w.height,
            "thickness": w.thickness,
        }
        for w in walls
    ]
