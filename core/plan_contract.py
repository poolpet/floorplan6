"""Stage 4 — kontrakt JSON rzutu (bundle-prep).

Jedna czysta, **AC-agnostyczna** funkcja `plan_to_contract(...)` produkująca słownik
`{meta, rooms, walls, doors, furniture, warnings}` — w pełni JSON-serializowalny
(zero Shapely/enum w wartościach). Woła go i lokalne GUI, i przyszła skorupa C++;
warstwa `bridge/` mapuje kontrakt na Tapir/ArchiCAD (GUID-y, payloady).

Reużywa istniejących extractorów core:
- ściany działowe: `core.wall_extractor.extract_internal_walls` (z samych pokoi),
- drzwi: `core.door_extractor.extract_doors` w trybie GUID-free (template.sasiedztwo),
- furniture: `core.furniture.FurnishResult`.

Pokoje/ściany/drzwi referują się po NAZWIE pokoju (`RoomSpec.nazwa`) — `rooms[]` niesie
i `id`, i `name`, więc konsument może mapować jedno na drugie.
"""
from __future__ import annotations

from core.models import FloorPlan
from core.wall_extractor import (
    DEFAULT_WALL_HEIGHT_M,
    DEFAULT_WALL_THICKNESS_M,
    extract_internal_walls,
)
from core.door_extractor import (
    DEFAULT_DOOR_HEIGHT,
    DEFAULT_DOOR_WIDTH,
    extract_doors,
)
from core.window_extractor import extract_facade_windows

CONTRACT_VERSION = 1


def _poly_coords(poly, nd: int = 3) -> list[list[float]]:
    """Obrys polygonu (zewnętrzny ring) jako [[x,y],...]; dla MultiPolygon — największy."""
    g = poly
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    return [[round(x, nd), round(y, nd)] for x, y in g.exterior.coords]


def plan_to_contract(
    rooms,
    boundary,
    furnish_result=None,
    *,
    storey: str = "parter",
    template=None,
    wall_height: float = DEFAULT_WALL_HEIGHT_M,
    wall_thickness: float = DEFAULT_WALL_THICKNESS_M,
    door_width: float = DEFAULT_DOOR_WIDTH,
    door_height: float = DEFAULT_DOOR_HEIGHT,
) -> dict:
    """Zbuduj kontrakt JSON rzutu (jednej kondygnacji).

    Args:
        rooms: lista Room (z polygonami).
        boundary: Boundary (bbox + polygon obrysu).
        furnish_result: FurnishResult (meble + ostrzeżenia); None → bez mebli.
        storey: etykieta kondygnacji ("parter"/"poddasze"/"single").
        template: Template z `sasiedztwo` → drzwi. None → drzwi=[] (ściany i tak są).
        wall_height/thickness, door_width/height: parametry geometryczne.

    Returns:
        dict {meta, rooms, walls, doors, furniture, warnings} — JSON-serializowalny.
    """
    valid_rooms = [r for r in rooms if r.polygon is not None]
    plan = FloorPlan(boundary=boundary, template=template, rooms=valid_rooms)

    walls = extract_internal_walls(plan, height=wall_height, thickness=wall_thickness)
    doors_seg = []
    if template is not None:
        doors_seg = extract_doors(
            plan, None, walls,
            width=door_width, height=door_height, wall_thickness=wall_thickness,
        )

    # centrum drzwi liczone z geometrii ściany (center_offset wzdłuż p1→p2)
    pair_to_wall = {frozenset((w.room_a, w.room_b)): w for w in walls if w.room_a and w.room_b}

    def _door_center(d):
        w = pair_to_wall.get(frozenset((d.room_a, d.room_b)))
        if w is None:
            return None
        (x1, y1), (x2, y2) = w.p1, w.p2
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        return [round(x1 + dx / length * d.center_offset, 3),
                round(y1 + dy / length * d.center_offset, 3)]

    windows = extract_facade_windows(valid_rooms, boundary)

    bx0, by0, bx1, by1 = boundary.bbox
    furniture = furnish_result.furniture if furnish_result is not None else []
    warnings = list(furnish_result.warnings) if furnish_result is not None else []

    return {
        "meta": {
            "contract_version": CONTRACT_VERSION,
            "storey": storey,
            "boundary_bbox": [round(bx0, 3), round(by0, 3), round(bx1, 3), round(by1, 3)],
            "boundary_polygon": _poly_coords(boundary.polygon),
        },
        "rooms": [{
            "id": r.spec.id,
            "name": r.spec.nazwa,
            "strefa": r.spec.strefa.value,
            "area": round(r.area, 2),
            "requires_window": bool(r.spec.wymaga_okna),
            "polygon": _poly_coords(r.polygon),
        } for r in valid_rooms],
        "walls": [{
            "p1": [round(w.p1[0], 3), round(w.p1[1], 3)],
            "p2": [round(w.p2[0], 3), round(w.p2[1], 3)],
            "room_a": w.room_a,
            "room_b": w.room_b,
            "height": round(w.height, 3),
            "thickness": round(w.thickness, 3),
        } for w in walls],
        "doors": [{
            "room_a": d.room_a,
            "room_b": d.room_b,
            "type": d.connection_type,
            "center": _door_center(d),
            "width": round(d.width, 3),
            "height": round(d.height, 3),
        } for d in doors_seg],
        "windows": [{
            "room_id": w.room_id,
            "room_name": w.room_name,
            "wall": w.wall,
            "center": [round(w.center[0], 3), round(w.center[1], 3)],
            "width": round(w.width, 3),
            "height": round(w.height, 3),
            "sill_height": round(w.sill_height, 3),
            "segment": [[round(w.p1[0], 3), round(w.p1[1], 3)],
                        [round(w.p2[0], 3), round(w.p2[1], 3)]],
        } for w in windows],
        "furniture": [{
            "type": f.piece_type,
            "label": f.label,
            "room_id": f.room_id,
            "polygon": _poly_coords(f.polygon),
        } for f in furniture],
        "warnings": warnings,
    }


def house_to_contract(layout, parter_furnish=None, pietro_furnish=None) -> dict:
    """Kontrakt całego domu z `TwoStoreyLayout` — produktowy wrapper (GUI / skorupa C++).

    Ładuje właściwe template'y (single / parter+poddasze) i woła `plan_to_contract`
    per kondygnacja. Zwraca {"parter": {...}} lub {"parter": {...}, "poddasze": {...}}.
    """
    from core.template_selector import load_all_templates  # lazy — nie ciągnij do importu core
    tpls = {t.id: t for t in load_all_templates()}
    single = not layout.pietro_rooms
    parter_tpl = tpls.get("house_single_storey") if single else tpls.get("house_parter")
    out = {
        "parter": plan_to_contract(
            layout.parter_rooms, layout.boundary, parter_furnish,
            storey="single" if single else "parter", template=parter_tpl,
        )
    }
    if layout.pietro_rooms:
        # Knee-wall (S26): poddasze żyje na PASIE przy kalenicy — okna/bbox kontraktu
        # liczone z attic_boundary, nie z pełnego obrysu parteru.
        pietro_b = getattr(layout, "attic_boundary", None) or layout.boundary
        out["poddasze"] = plan_to_contract(
            layout.pietro_rooms, pietro_b, pietro_furnish,
            storey="poddasze", template=tpls.get("house_pietro"),
        )
    return out
