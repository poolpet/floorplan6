"""
Obsługa trapezów — solver działa na wpisanym prostokącie,
potem pokoje są rozciągane do ścian trapezu.

Algorytm:
1. Wykryj trapez (4 wierzchołki, 1 para boków równoległych)
2. Wpisz największy prostokąt (baza = krótszy bok równoległy)
3. Solver generuje rzut w prostokącie
4. Rozciągnij pokoje brzegowe do ścian trapezu (magnes)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from shapely.geometry import Polygon, box as sbox

from core.models import Room, FloorPlan


@dataclass
class TrapezoidInfo:
    """Opis trapezu — orientacja i wymiary."""
    # Dwa boki równoległe (dolny = baza, górny = szczyt)
    base_y: float       # y dolnego boku (bliżej entry)
    top_y: float        # y górnego boku
    base_left_x: float  # lewy koniec dolnego boku
    base_right_x: float # prawy koniec dolnego boku
    top_left_x: float   # lewy koniec górnego boku
    top_right_x: float  # prawy koniec górnego boku

    @property
    def height(self) -> float:
        return abs(self.top_y - self.base_y)

    @property
    def base_width(self) -> float:
        return self.base_right_x - self.base_left_x

    @property
    def top_width(self) -> float:
        return self.top_right_x - self.top_left_x

    @property
    def shorter_width(self) -> float:
        return min(self.base_width, self.top_width)

    def left_wall_x_at(self, y: float) -> float:
        """X lewej ściany trapezu na wysokości y."""
        t = (y - self.base_y) / self.height if self.height > 0 else 0
        return self.base_left_x + t * (self.top_left_x - self.base_left_x)

    def right_wall_x_at(self, y: float) -> float:
        """X prawej ściany trapezu na wysokości y."""
        t = (y - self.base_y) / self.height if self.height > 0 else 0
        return self.base_right_x + t * (self.top_right_x - self.base_right_x)


def detect_trapezoid(polygon: Polygon) -> Optional[TrapezoidInfo]:
    """Wykryj trapez (4 wierzchołki, 1 para boków równoległych — poziomych).

    Returns:
        TrapezoidInfo lub None jeśli to nie trapez.
    """
    coords = list(polygon.exterior.coords)
    if coords[-1] == coords[0]:
        coords = coords[:-1]

    if len(coords) != 4:
        return None

    # Znajdź pary boków równoległych (poziomych: dy ≈ 0)
    edges = []
    for i in range(4):
        p1 = coords[i]
        p2 = coords[(i + 1) % 4]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        edges.append((p1, p2, dx, dy))

    # Szukaj "najbardziej poziomych" boków — 2 boki z najmniejszym |dy/dx|
    edge_slopes = []
    for i, (p1, p2, dx, dy) in enumerate(edges):
        length = math.hypot(dx, dy)
        slope = abs(dy) / length if length > 0 else 999
        edge_slopes.append((slope, i, p1, p2))

    edge_slopes.sort(key=lambda e: e[0])
    # Dwa najbardziej poziome boki (kąt < ~15° od poziomu)
    horizontal = []
    for slope, i, p1, p2 in edge_slopes[:2]:
        if slope < 0.26:  # sin(15°) ≈ 0.26
            horizontal.append((i, p1, p2))

    if len(horizontal) != 2:
        return None  # nie ma dokładnie 2 poziomych boków

    # Dolny i górny bok
    h1_idx, h1_p1, h1_p2 = horizontal[0]
    h2_idx, h2_p1, h2_p2 = horizontal[1]

    y1 = (h1_p1[1] + h1_p2[1]) / 2
    y2 = (h2_p1[1] + h2_p2[1]) / 2

    if y1 > y2:
        # Zamień — dolny musi mieć mniejsze y
        h1_p1, h1_p2, h2_p1, h2_p2 = h2_p1, h2_p2, h1_p1, h1_p2
        y1, y2 = y2, y1

    return TrapezoidInfo(
        base_y=y1,
        top_y=y2,
        base_left_x=min(h1_p1[0], h1_p2[0]),
        base_right_x=max(h1_p1[0], h1_p2[0]),
        top_left_x=min(h2_p1[0], h2_p2[0]),
        top_right_x=max(h2_p1[0], h2_p2[0]),
    )


def inscribed_rectangle(trap: TrapezoidInfo) -> Polygon:
    """Największy prostokąt wpisany w trapez (boki pionowe).

    Lewy bok = max lewych ścian trapezu (najwęższy punkt lewej strony).
    Prawy bok = min prawych ścian trapezu (najwęższy punkt prawej strony).
    Gwarantuje że prostokąt jest w 100% wewnątrz trapezu.
    """
    # Najwęższy punkt na lewej stronie (max x)
    x_left = max(trap.base_left_x, trap.top_left_x)
    # Najwęższy punkt na prawej stronie (min x)
    x_right = min(trap.base_right_x, trap.top_right_x)

    y0 = trap.base_y
    y1 = trap.top_y

    return sbox(x_left, y0, x_right, y1)


def stretch_rooms_to_trapezoid(
    plan: FloorPlan,
    trap: TrapezoidInfo,
    rect: Polygon,
) -> FloorPlan:
    """Rozciągnij pokoje z prostokąta do ścian trapezu.

    Pokoje dotykające lewej/prawej ściany prostokąta → ich krawędzie
    przesuwają się do ukośnych ścian trapezu.
    """
    rb = rect.bounds  # (x0, y0, x1, y1)
    rect_left = rb[0]
    rect_right = rb[2]
    tol = 0.05  # 5cm tolerancja

    new_rooms = []
    for room in plan.rooms:
        if room.polygon is None:
            new_rooms.append(room)
            continue

        b = room.polygon.bounds  # (rx0, ry0, rx1, ry1)
        rx0, ry0, rx1, ry1 = b

        # Czy pokój dotyka lewej ściany prostokąta?
        touches_left = abs(rx0 - rect_left) < tol
        # Czy pokój dotyka prawej ściany prostokąta?
        touches_right = abs(rx1 - rect_right) < tol

        if not touches_left and not touches_right:
            # Pokój wewnętrzny — bez zmian
            new_rooms.append(room)
            continue

        # Zbuduj nowy polygon z rozciągniętymi krawędziami
        if touches_left:
            new_x0_bottom = trap.left_wall_x_at(ry0)
            new_x0_top = trap.left_wall_x_at(ry1)
        else:
            new_x0_bottom = rx0
            new_x0_top = rx0

        if touches_right:
            new_x1_bottom = trap.right_wall_x_at(ry0)
            new_x1_top = trap.right_wall_x_at(ry1)
        else:
            new_x1_bottom = rx1
            new_x1_top = rx1

        # Nowy polygon (trapezoidalny pokój)
        new_poly = Polygon([
            (new_x0_bottom, ry0),  # lewy-dolny
            (new_x1_bottom, ry0),  # prawy-dolny
            (new_x1_top, ry1),     # prawy-górny
            (new_x0_top, ry1),     # lewy-górny
        ])

        if new_poly.is_valid and new_poly.area > 0.1:
            new_room = Room(spec=room.spec, polygon=new_poly)
            new_room.update_metrics()
            new_rooms.append(new_room)
        else:
            new_rooms.append(room)

    # Przelicz boundary na trapez
    trap_poly = Polygon([
        (trap.base_left_x, trap.base_y),
        (trap.base_right_x, trap.base_y),
        (trap.top_right_x, trap.top_y),
        (trap.top_left_x, trap.top_y),
    ])
    plan.boundary.polygon = trap_poly

    # Docinaj pokoje do obrysu trapezu (żaden nie może wystawać)
    clipped_rooms = []
    for room in new_rooms:
        if room.polygon is None:
            clipped_rooms.append(room)
            continue
        clipped = room.polygon.intersection(trap_poly)
        if clipped.is_empty or clipped.area < 0.1:
            clipped_rooms.append(room)
            continue
        # Weź największy polygon z wyniku (intersection może dać MultiPolygon)
        if clipped.geom_type == "MultiPolygon":
            clipped = max(clipped.geoms, key=lambda g: g.area)
        elif clipped.geom_type != "Polygon":
            clipped_rooms.append(room)
            continue
        new_room = Room(spec=room.spec, polygon=clipped)
        new_room.update_metrics()
        clipped_rooms.append(new_room)

    plan.rooms = clipped_rooms
    return plan
