"""
Analiza obrysu mieszkania — Krok 1 algorytmu outside-in.

Klasyfikacja krawędzi (FACADE/INTERNAL), segmenty fasadowe, orientacja.
MVP: TYLKO prostokąty (RYZYKO 5 z CLAUDE.md).
"""
from __future__ import annotations

from shapely.geometry import Polygon, Point

from core.models import (
    Boundary, EdgeInfo, FacadeSegment, NotchInfo, WallType, Orientation,
)


# Tolerancja prostokątności: MRR.area / polygon.area < 1 + tol
RECT_TOLERANCE = 0.05


def is_rectangle(polygon: Polygon, tolerance: float = RECT_TOLERANCE) -> bool:
    """Sprawdź czy wielokąt jest prostokątem (z tolerancją)."""
    mrr = polygon.minimum_rotated_rectangle
    return mrr.area / polygon.area < (1.0 + tolerance)


def _classify_edges_rectangle(
    coords: list[tuple[float, float]],
    entry_point: tuple[float, float],
    wall_types: list[WallType] | None = None,
) -> list[EdgeInfo]:
    """Klasyfikuj krawędzie prostokąta.

    Domyślnie: krawędź z entry_point = INTERNAL, reszta = FACADE.
    Jeśli wall_types podane — użyj ich.
    """
    edges = []
    for i in range(len(coords) - 1):
        start = coords[i]
        end = coords[i + 1]

        if wall_types and i < len(wall_types):
            wt = wall_types[i]
        else:
            # Domyślna heurystyka: krawędź blisko entry_point = INTERNAL
            wt = WallType.FACADE

        edge = EdgeInfo(start=start, end=end, wall_type=wt)
        edges.append(edge)

    # Oznacz krawędź z drzwiami wejściowymi jako INTERNAL
    if wall_types is None:
        _mark_entry_edge(edges, entry_point)

    return edges


def _mark_entry_edge(edges: list[EdgeInfo], entry_point: tuple[float, float]) -> int:
    """Znajdź krawędź najbliższą entry_point i oznacz jako INTERNAL.

    Zwraca indeks krawędzi z drzwiami.
    """
    ep = Point(entry_point)
    best_idx = 0
    best_dist = float("inf")

    for i, edge in enumerate(edges):
        dist = edge.line.distance(ep)
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    edges[best_idx].wall_type = WallType.INTERNAL
    return best_idx


def _build_facade_segments(edges: list[EdgeInfo]) -> list[FacadeSegment]:
    """Zbuduj ciągłe segmenty fasadowe z krawędzi FACADE."""
    segments = []
    current_edges: list[EdgeInfo] = []

    for edge in edges:
        if edge.wall_type == WallType.FACADE:
            if current_edges and current_edges[-1].orientation != edge.orientation:
                # Nowy segment — inna orientacja
                segments.append(FacadeSegment(
                    edges=current_edges,
                    orientation=current_edges[0].orientation,
                ))
                current_edges = []
            current_edges.append(edge)
        else:
            if current_edges:
                segments.append(FacadeSegment(
                    edges=current_edges,
                    orientation=current_edges[0].orientation,
                ))
                current_edges = []

    if current_edges:
        segments.append(FacadeSegment(
            edges=current_edges,
            orientation=current_edges[0].orientation,
        ))

    return segments


def _remove_collinear_vertices(coords: list[tuple[float, float]], tol: float = 0.01) -> list[tuple[float, float]]:
    """Usuń wierzchołki kolinearne (3 kolejne punkty na jednej linii prostej).

    Tapir Zone z AC może zwrócić redundant punkty — np. ślad podziału ścian.
    """
    n = len(coords)
    if n < 4:
        return list(coords)
    keep = []
    for i in range(n):
        p_prev = coords[(i - 1) % n]
        p_curr = coords[i]
        p_next = coords[(i + 1) % n]
        # Cross product: jeśli ≈ 0 → kolinearne
        cross = ((p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1])
                 - (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0]))
        if abs(cross) > tol:
            keep.append(p_curr)
    return keep


def _detect_notch(polygon: Polygon) -> NotchInfo | list[NotchInfo] | None:
    """Wykryj wycięcia w kształcie (L, U lub prostokąt z wycięciem).

    Obsługuje:
    - L-kształt (6 wierzchołków, 1 notch w rogu)
    - U-kształt (8 wierzchołków, 1 notch na boku)

    Returns:
        NotchInfo (jeden notch) lub None.
    """
    if is_rectangle(polygon):
        return None

    coords = list(polygon.exterior.coords)
    if coords[-1] == coords[0]:
        coords = coords[:-1]

    # Usuń kolinearne wierzchołki (Zone z AC może mieć redundant punkty na granicach
    # ścian — 3 kolejne punkty na tej samej linii prostej).
    coords = _remove_collinear_vertices(coords)

    # Tylko 6 lub 8 wierzchołków (L lub U)
    if len(coords) not in (6, 8):
        return None

    # Sprawdź osiowe wyrównanie (wszystkie krawędzie poziome lub pionowe)
    for i in range(len(coords)):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % len(coords)]
        if abs(x1 - x2) > 0.01 and abs(y1 - y2) > 0.01:
            return None  # krawędź ukośna

    # Bounding box
    bx0, by0, bx1, by1 = polygon.bounds

    # Notch = różnica bbox - polygon
    from shapely.geometry import box as sbox
    bbox_poly = sbox(bx0, by0, bx1, by1)
    notch_poly = bbox_poly.difference(polygon)

    if notch_poly.is_empty or notch_poly.area < 0.1:
        return None

    # Notch musi być prostokątem (jedno wycięcie)
    nb = notch_poly.bounds
    notch_rect_area = (nb[2] - nb[0]) * (nb[3] - nb[1])
    if abs(notch_poly.area - notch_rect_area) > 0.05:
        return None  # wycięcie nie jest prostokątne

    return NotchInfo(
        x=nb[0] - bx0,
        y=nb[1] - by0,
        width=nb[2] - nb[0],
        height=nb[3] - nb[1],
    )


def analyze_boundary(
    polygon: Polygon,
    entry_point: tuple[float, float],
    wall_types: list[WallType] | None = None,
    orientation_north: float = 0.0,
) -> Boundary:
    """Analizuj obrys mieszkania.

    Args:
        polygon: Wielokąt obrysu (Shapely Polygon).
        entry_point: Pozycja drzwi wejściowych (x, y) w metrach.
        wall_types: Opcjonalna lista typów ścian (FACADE/INTERNAL) per krawędź.
        orientation_north: Kąt obrotu mapy (0 = góra = N).

    Returns:
        Boundary z klasyfikacją krawędzi i segmentami fasadowymi.
    """
    # Współrzędne (Shapely daje zamknięty ring — ostatni punkt = pierwszy)
    coords = list(polygon.exterior.coords)

    # Klasyfikuj krawędzie
    edges = _classify_edges_rectangle(coords, entry_point, wall_types)

    # Znajdź indeks krawędzi z drzwiami
    ep = Point(entry_point)
    entry_idx = min(range(len(edges)), key=lambda i: edges[i].line.distance(ep))

    # Detekcja L/U-kształtu
    notch = _detect_notch(polygon)

    boundary = Boundary(
        polygon=polygon,
        edges=edges,
        entry_point=entry_point,
        entry_edge_idx=entry_idx,
        orientation_north=orientation_north,
        notch=notch,
    )

    return boundary


def get_facade_segments(boundary: Boundary) -> list[FacadeSegment]:
    """Zwróć posortowane segmenty fasadowe (najlepsza fasada pierwsza)."""
    segments = _build_facade_segments(boundary.edges)
    segments.sort(key=lambda s: s.score, reverse=True)
    return segments


# ============================================================
# CLI — test
# ============================================================

if __name__ == "__main__":
    # Test: prostokąt 8×6m, drzwi na dole (ściana wewnętrzna = dolna)
    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    entry = (4.0, 0.0)  # środek dolnej krawędzi

    boundary = analyze_boundary(poly, entry)
    segments = get_facade_segments(boundary)

    print(f"Boundary: {boundary.width:.1f} × {boundary.height:.1f} m")
    print(f"Area: {boundary.area:.1f} m²")
    print(f"Entry edge: #{boundary.entry_edge_idx}")
    print()

    for i, edge in enumerate(boundary.edges):
        print(f"  Edge {i}: {edge.start} → {edge.end}  "
              f"len={edge.length:.1f}m  type={edge.wall_type.value}  "
              f"orient={edge.orientation.value}")

    print()
    print(f"Segmenty fasadowe ({len(segments)}):")
    for seg in segments:
        print(f"  {seg.orientation.value}: {seg.total_length:.1f}m  "
              f"quality={seg.quality:.2f}  score={seg.score:.2f}")
