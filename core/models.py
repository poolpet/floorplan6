"""
FloorPlanEngine — modele danych.

Dataclasses: Boundary, EdgeInfo, FacadeSegment, RoomSpec, Room, Template, FloorPlan, SourcePlan.
Przygotowane na rozszerzenie o klasyfikację ścian zew/wew i nowe rzuty.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from shapely.geometry import Polygon, LineString, Point


# ============================================================
# Enums
# ============================================================

class WallType(str, Enum):
    """Typ ściany — INPUT od użytkownika lub z ArchiCAD."""
    FACADE = "FACADE"           # ściana zewnętrzna (okno możliwe)
    INTERNAL = "INTERNAL"       # ściana wewnętrzna (sąsiad / klatka)
    UNKNOWN = "UNKNOWN"         # jeszcze niesklasyfikowana


class Orientation(str, Enum):
    N = "N"; NE = "NE"; E = "E"; SE = "SE"
    S = "S"; SW = "SW"; W = "W"; NW = "NW"


class Strefa(str, Enum):
    DZIENNA = "DZIENNA"
    NOCNA = "NOCNA"
    USLUGOWA = "USŁUGOWA"
    KOMUNIKACJA = "KOMUNIKACJA"

    @property
    def display(self) -> str:
        """English display name for UI (legend, exports)."""
        return {
            "DZIENNA": "DAY",
            "NOCNA": "NIGHT",
            "USŁUGOWA": "SERVICE",
            "KOMUNIKACJA": "CIRCULATION",
        }[self.value]


# ============================================================
# Boundary — obrys mieszkania
# ============================================================

@dataclass
class EdgeInfo:
    """Jedna krawędź obrysu wielokąta."""
    start: tuple[float, float]
    end: tuple[float, float]
    wall_type: WallType = WallType.UNKNOWN
    orientation: Optional[Orientation] = None
    length: float = 0.0

    def __post_init__(self):
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        self.length = math.hypot(dx, dy)
        if self.orientation is None:
            self.orientation = self._compute_outward_orientation(dx, dy)

    @staticmethod
    def _compute_outward_orientation(dx: float, dy: float) -> Orientation:
        """Orientacja normali zewnętrznej krawędzi (kierunek świata fasady)."""
        # Normalna: obrót o 90° w prawo (dla wielokąta CCW → normalna na zewnątrz)
        nx, ny = dy, -dx
        angle = math.degrees(math.atan2(ny, nx)) % 360
        dirs = [
            (0, Orientation.E), (45, Orientation.NE), (90, Orientation.N),
            (135, Orientation.NW), (180, Orientation.W), (225, Orientation.SW),
            (270, Orientation.S), (315, Orientation.SE),
        ]
        best = min(dirs, key=lambda d: min(abs(angle - d[0]), 360 - abs(angle - d[0])))
        return best[1]

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2,
                (self.start[1] + self.end[1]) / 2)

    @property
    def line(self) -> LineString:
        return LineString([self.start, self.end])


@dataclass
class FacadeSegment:
    """Ciągły odcinek fasady (kilka krawędzi o zbliżonej orientacji)."""
    edges: list[EdgeInfo]
    orientation: Orientation
    total_length: float = 0.0
    quality: float = 0.0

    def __post_init__(self):
        self.total_length = sum(e.length for e in self.edges)
        from config import ORIENTATION_QUALITY
        self.quality = ORIENTATION_QUALITY.get(self.orientation.value, 0.5)

    @property
    def score(self) -> float:
        """Ranking: długość × jakość orientacji."""
        return self.total_length * self.quality

    @property
    def start(self) -> tuple[float, float]:
        return self.edges[0].start if self.edges else (0, 0)

    @property
    def end(self) -> tuple[float, float]:
        return self.edges[-1].end if self.edges else (0, 0)


@dataclass
class NotchInfo:
    """Wycięcie w L-kształcie — prostokąt do odjęcia od bounding box."""
    x: float       # lewy dolny róg wycięcia (metry, relative to bbox origin)
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class Boundary:
    """Obrys mieszkania — wielokąt + krawędzie + punkt wejścia."""
    polygon: Polygon
    edges: list[EdgeInfo]
    entry_point: tuple[float, float]
    entry_edge_idx: Optional[int] = None
    orientation_north: float = 0.0  # kąt obrotu: 0 = góra=N
    notch: Optional[NotchInfo] = None  # wycięcie L-kształtu
    # Klasyfikacja wewnętrznych krawędzi notch (te które są WIDOCZNE z polygonu,
    # tj. nie zlewają się z bbox boundary). Klucze: "upper"/"lower"/"left"/"right"
    # z perspektywy notch (krawędź notch_top widziana z polygonu = upper itp.).
    # True = FACADE (pokój z oknem może mieć krawędź na tej linii).
    notch_facades: dict = field(default_factory=dict)

    @property
    def area(self) -> float:
        return self.polygon.area

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.polygon.bounds

    @property
    def width(self) -> float:
        b = self.bbox
        return b[2] - b[0]

    @property
    def height(self) -> float:
        b = self.bbox
        return b[3] - b[1]

    @property
    def facade_edges(self) -> list[EdgeInfo]:
        return [e for e in self.edges if e.wall_type == WallType.FACADE]

    @property
    def internal_edges(self) -> list[EdgeInfo]:
        return [e for e in self.edges if e.wall_type == WallType.INTERNAL]


# ============================================================
# Room spec (z szablonu) i Room (wygenerowany)
# ============================================================

@dataclass
class RoomSpec:
    """Specyfikacja pokoju z szablonu topologicznego."""
    id: str                          # "salon", "sypialnia_1", "hub"
    nazwa: str                       # "Pokój dzienny z aneksem kuchennym"
    strefa: Strefa
    wymaga_okna: bool
    priorytet_fasady: Optional[int]  # None = pokój wewnętrzny (łazienka, hub)
    preferowana_orientacja: list[Orientation] = field(default_factory=list)
    min_powierzchnia: float = 0.0
    opt_powierzchnia: float = 0.0    # wyuczona z danych
    min_szerokosc: float = 0.0
    max_proporcja: float = 2.0
    procent_powierzchni: tuple[float, float] = (0.0, 1.0)


@dataclass
class Room:
    """Wygenerowany pokój z geometrią."""
    spec: RoomSpec
    polygon: Optional[Polygon] = None
    facade_segment_idx: Optional[int] = None
    area: float = 0.0
    width: float = 0.0
    depth: float = 0.0
    proportion: float = 1.0

    def update_metrics(self):
        """Przelicz metryki z polygonu."""
        if self.polygon is not None:
            self.area = self.polygon.area
            b = self.polygon.bounds
            w = b[2] - b[0]
            h = b[3] - b[1]
            self.width = min(w, h)
            self.depth = max(w, h)
            self.proportion = self.depth / self.width if self.width > 0 else 999


# ============================================================
# Template — szablon topologiczny
# ============================================================

@dataclass
class AdjacencyRule:
    """Połączenie w grafie sąsiedztwa."""
    room_a: str
    room_b: str
    connection_type: str = "door"  # "door", "opening", "entry_door"


@dataclass
class Template:
    """Szablon topologiczny mieszkania — graf pokoi + reguły strefowe."""
    id: str
    nazwa: str
    typ_mieszkania: str  # "M1"..."M5"
    pokoje: list[RoomSpec]
    sasiedztwo: list[AdjacencyRule]
    source: str = "manual"       # "manual" | "extracted" | "statistical"
    confidence: float = 1.0
    n_source_plans: int = 0      # z ilu rzutów wyekstrahowany

    @property
    def room_ids(self) -> list[str]:
        return [p.id for p in self.pokoje]

    def get_room(self, room_id: str) -> Optional[RoomSpec]:
        for p in self.pokoje:
            if p.id == room_id:
                return p
        return None


# ============================================================
# FloorPlan — wygenerowany rzut (wynik)
# ============================================================

@dataclass
class FloorPlan:
    """Kompletny wygenerowany rzut mieszkania."""
    boundary: Boundary
    template: Template
    rooms: list[Room]
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    @property
    def total_room_area(self) -> float:
        return sum(r.area for r in self.rooms)

    @property
    def hub_room(self) -> Optional[Room]:
        for r in self.rooms:
            if r.spec.strefa == Strefa.KOMUNIKACJA:
                return r
        return None

    @property
    def usable_area(self) -> float:
        """Faktyczna powierzchnia użytkowa (suma pokoi lub boundary, co mniejsze).

        Dla planów generowanych: usable_area == boundary.area (perfect tiling).
        Dla planów z danych: usable_area == suma pokoi (bbox > suma pokoi o 10-49%).
        """
        room_sum = self.total_room_area
        if room_sum > 0 and room_sum < self.boundary.area:
            return room_sum
        return self.boundary.area

    @property
    def hub_percent(self) -> float:
        hub = self.hub_room
        if hub is None:
            return 0.0
        return hub.area / self.usable_area if self.usable_area > 0 else 0


# ============================================================
# SourcePlan — rzut źródłowy do uczenia
# ============================================================

@dataclass
class SourcePlan:
    """Rzut źródłowy z datasetu — do ekstrakcji szablonów i statystyk.

    Pola wall_types i entry_position są opcjonalne — zostaną dodane
    w późniejszej fazie, gdy ręcznie oznaczysz ściany na rzutach.
    """
    id: str
    source_file: str
    apartment_type: str              # "M1"..."M5"
    total_area_m2: float
    width_m: float
    height_m: float
    rooms: list[dict]                # surowe dane pokoi z JSON
    edges: list[dict]                # graf połączeń (drzwi/otwory)
    wall_types: Optional[list[WallType]] = None   # TODO: dodać później
    entry_position: Optional[tuple[float, float]] = None  # TODO: dodać później
    metadata: dict = field(default_factory=dict)
