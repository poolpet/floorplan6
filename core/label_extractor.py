"""
Ekstrakcja etykiet pokoi z wygenerowanego rzutu (V3 — Tapir 1.4.0).

Dla każdego pokoju tworzymy associative label podpiętą do utworzonej
Zone (parentElementId = zone_guid). Tekst label = nazwa pokoju + powierzchnia.

Tapir CreateLabels schema:
    parentElementId: ElementId (opcjonalne — dla associative label)
    text:            string  (zawartość)
    begCoordinate:   {x, y}  (początek linii odniesienia)
    floorInd:        number  (opcjonalne)
Wymagane: jeden z parentElementId / begCoordinate.

Format tekstu:
    "{nazwa pokoju}\n{powierzchnia:.1f} m²"
np.:
    "Salon\n24.5 m²"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.models import FloorPlan


@dataclass
class LabelSegment:
    """Etykieta jednego pokoju."""
    text: str
    beg_x: float          # początek linii odniesienia (centroid pokoju)
    beg_y: float
    parent_zone_guid: Optional[str] = None   # GUID Zone z CreateZones (associative label)
    room_name: str = ""                       # diagnostyka


def extract_labels(
    plan: FloorPlan,
    zone_guids: Optional[list[str]] = None,
) -> list[LabelSegment]:
    """Wyciągnij listę etykiet dla każdego pokoju w rzucie.

    Args:
        plan: Wygenerowany FloorPlan.
        zone_guids: Lista GUID-ów Zone z CreateZones, w tej samej kolejności
            co `plan.rooms`. Jeśli podana, label powstaje jako associative
            (parentElementId = zone_guid). Jeśli None — label free-standing.

    Returns:
        Lista LabelSegment dla pokoi które mają polygon i area > 0.
    """
    labels: list[LabelSegment] = []

    # Mapping room idx → zone guid (jeśli mamy)
    room_idx_to_guid: dict[int, str] = {}
    if zone_guids:
        # zone_guids są w kolejności rooms WITH polygon (skipuje rooms bez polygon).
        # Musimy ten sam filter zastosować.
        valid_rooms = [(i, r) for i, r in enumerate(plan.rooms) if r.polygon is not None]
        for (orig_idx, _), guid in zip(valid_rooms, zone_guids):
            if guid:
                room_idx_to_guid[orig_idx] = guid

    for i, room in enumerate(plan.rooms):
        if room.polygon is None:
            continue

        geom = room.polygon
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        centroid = geom.centroid

        area = geom.area
        if area <= 0:
            continue

        # Format: "Nazwa\nXX.X m²"
        text = f"{room.spec.nazwa}\n{area:.1f} m²"  # ² = ²

        labels.append(LabelSegment(
            text=text,
            beg_x=centroid.x,
            beg_y=centroid.y,
            parent_zone_guid=room_idx_to_guid.get(i),
            room_name=room.spec.nazwa,
        ))

    return labels


def labels_to_tapir_payload(labels: list[LabelSegment]) -> list[dict]:
    """Konwertuje do formatu Tapir CreateLabels.

    Tapir 1.4.0 CreateLabels schema:
        parentElementId (optional), text (optional), begCoordinate (optional),
        floorInd (optional). Wymagane: jeden z parentElementId / begCoordinate.
    Dajemy oba — associative + leader line position.
    """
    out = []
    for label in labels:
        payload: dict = {
            "text": label.text,
            "begCoordinate": {
                "x": round(label.beg_x, 6),
                "y": round(label.beg_y, 6),
            },
        }
        if label.parent_zone_guid:
            payload["parentElementId"] = {"guid": label.parent_zone_guid}
        out.append(payload)
    return out
