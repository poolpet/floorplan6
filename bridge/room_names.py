"""Polish room/template names -> English, for everything the user can see.

`core/` is frozen: `RoomSpec.nazwa` and the template names in `templates/*.json`
stay Polish (they are also solver-facing identifiers). Beta testers are not
Polish speakers (spec 2026-09-15 §9), so every seam that shows a name to a human
— Archicad zone names and labels, the matplotlib preview, the GUI details panel —
runs it through `room_name_en()` first.

Names that are already English pass through unchanged, so mixed templates
(apartments are English, houses are Polish) need no special casing.

NOT a translation of the internal storey KEYS: `parter` / `poddasze` are contract
keys between `ui/`, `core/` and `bridge/house_writer` and must never be mapped on
the way into the solver — only on the way to a caption.
"""
from __future__ import annotations

ROOM_NAMES_EN: dict[str, str] = {
    # ── rooms (templates/*.json -> pokoje[].nazwa) ──
    "Salon": "Living room",
    "Pokój dzienny": "Living room",
    "Pokój z aneksem kuchennym": "Living room with kitchenette",
    "Kuchnia": "Kitchen",
    "Aneks kuchenny": "Kitchenette",
    "Jadalnia": "Dining room",
    "Sypialnia": "Bedroom",
    "Sypialnia główna": "Master bedroom",
    "Sypialnia (parter)": "Bedroom (ground floor)",
    "Sypialnia 2": "Bedroom 2",
    "Sypialnia 3": "Bedroom 3",
    "Sypialnia 4": "Bedroom 4",
    "Pokój": "Room",
    "Pokój dziecięcy": "Children's room",
    "Łazienka": "Bathroom",
    "Łazienka 2": "Bathroom 2",
    "Łazienka główna": "Main bathroom",
    "WC": "WC",
    "Przedpokój": "Hall",
    "Hol": "Hall",
    "Hol / podest": "Hall / landing",
    "Korytarz": "Corridor",
    "Wiatrołap": "Vestibule",
    "Przedsionek": "Vestibule",
    "Garderoba": "Wardrobe",
    "Spiżarnia": "Pantry",
    "Kotłownia": "Utility room",
    "Pralnia": "Laundry",
    "Gabinet": "Study",
    "Garaż": "Garage",
    "Schody": "Stairs",
    "Klatka schodowa": "Staircase",
    "Taras": "Terrace",
    "Balkon": "Balcony",
    "Piwnica": "Basement",
    "Strych": "Loft",
    # ── whole templates (templates/*.json -> nazwa) ──
    "Kawalerka standardowa": "Studio standard",
    "3-pokojowe z WC": "3-room with WC",
    "Dom jednorodzinny — parter": "Single-family house — ground floor",
    "Dom jednorodzinny — piętro": "Single-family house — first floor",
    "Dom jednorodzinny — parterowy": "Single-family house — single storey",
    "Dom jednorodzinny 2-kondygnacyjny": "Two-storey single-family house",
    # ── storeys (captions only — NOT the internal `parter`/`poddasze` keys) ──
    "parter": "Ground floor",
    "poddasze": "Attic",
    "piętro": "First floor",
    "PARTER": "GROUND FLOOR",
    "PODDASZE": "ATTIC",
    "PIĘTRO": "FIRST FLOOR",
}


def room_name_en(name: str) -> str:
    """English name for a room/template/storey; unknown or already-English input
    comes back unchanged (so a name added to `core/` never crashes the export)."""
    if not name:
        return name
    return ROOM_NAMES_EN.get(name, name)
