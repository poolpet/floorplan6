"""Multi-obrys eksport do ArchiCAD: wygeneruj i wstaw rozkład pokoi + MEBLE dla
KAŻDEGO zaznaczonego obrysu osobno (test wielu obrysów naraz — szybkie wyłapanie
problemów, prośba Dawida 2026-06-08).

Reader produktu (`read_boundary_from_archicad`) czyta JEDEN obrys (zlepia wszystkie
zaznaczone ściany w jeden polygon, a przy Zone/Slab bierze pierwszy). Tu obsługujemy
WIELE obrysów:
    • każda zaznaczona Zone/Slab = osobny obrys (reuse _read_boundary_from_zone_or_slab),
    • same ściany (bez Zone/Slab) = 1 zlepiony obrys (jak dotąd) — z notką.

Każdy obrys: shift do (0,0) → generate_variants (M-fallback) → export_plan_to_archicad
z offsetem = róg-świata tego obrysu (ląduje w SWOIM miejscu, obrysy się nie nakładają).
include_furniture=True → meble z fixami H1 (aneks kuchenny) + H2 (orientacja, anti-float).

Uruchom z AC + Tapir, MAJĄC ZAZNACZONE kilka obrysów (najlepiej Zone per obrys,
albo Slab; ew. ściany jednego obrysu):
    PYTHONPATH=. venv/bin/python notebooks/ac_export_multi.py

Drukuje skład zaznaczenia + per-obrys: bounds/pole/typ-M/liczniki (strefy/ścianki/
drzwi/okna/MEBLE) lub powód pominięcia.
"""
from __future__ import annotations

from collections import Counter

from shapely.affinity import translate

from core.variant_generator import generate_variants

MTYPE_FALLBACK = ["M3", "M2", "M4", "M1", "M5"]


def _guid(elem):
    if isinstance(elem, dict):
        eid = elem.get("elementId", elem)
        return eid.get("guid") if isinstance(eid, dict) else str(eid)
    return str(elem)


def _snap(p):
    return (round(p[0] * 20) / 20, round(p[1] * 20) / 20)  # 5 cm


def _wall_components(walls):
    """Pogrupuj ściany [(guid, beg, end)] w komponenty spójności (osobne pętle/obrysy)."""
    from collections import defaultdict
    node_walls = defaultdict(list)
    for idx, (_g, beg, end) in enumerate(walls):
        node_walls[_snap(beg)].append(idx)
        node_walls[_snap(end)].append(idx)
    adj = defaultdict(set)
    for idxs in node_walls.values():
        for a in idxs:
            for b in idxs:
                if a != b:
                    adj[a].add(b)
        # połącz też ściany dzielące węzeł, nawet jeśli to jedyne na węźle (no-op)
    # BFS po INDEKSACH ścian, łącząc te które dzielą węzeł
    # (zbuduj graf ścian: dwie ściany sąsiadują jeśli mają wspólny węzeł)
    seen = set()
    comps = []
    for start in range(len(walls)):
        if start in seen:
            continue
        stack = [start]
        comp = []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.append(x)
            stack += [y for y in adj[x] if y not in seen]
        comps.append(comp)
    return comps


def _collect_outlines(tapir, details, guids):
    """Zwróć listę (polygon, entry, wall_types, label) — po jednym na obrys.

    Zone/Slab → każdy = osobny obrys. Same ściany → grupuj w komponenty spójności
    (każda zamknięta pętla = osobny obrys), z przypisaniem drzwi per komponent.
    """
    from shapely.geometry import Polygon
    from bridge.boundary_reader import (
        _read_boundary_from_zone_or_slab,
        _chain_segments,
        _detect_entry_from_door,
        _detect_entry_and_wall_types,
    )
    zone_slabs = [d for d in details if isinstance(d, dict) and d.get("type") in ("Zone", "Slab")]
    outlines = []
    if zone_slabs:
        for i, d in enumerate(zone_slabs):
            try:
                polygon, entry, wt = _read_boundary_from_zone_or_slab(tapir, d)
                outlines.append((polygon, entry, wt, f"{d.get('type')}#{i + 1}"))
            except Exception as e:
                print(f"  • {d.get('type')}#{i + 1}: POMINIĘTY ({e})")
        return outlines, "zone/slab"

    # same ściany → komponenty spójności = osobne obrysy
    walls = []            # (guid, beg, end)
    door_owners = []      # guid ściany-właściciela drzwi
    for g, d in zip(guids, details):
        if not isinstance(d, dict):
            continue
        if d.get("type") == "Door":
            owner = d.get("details", {}).get("ownerElementId", {})
            og = owner.get("guid") if isinstance(owner, dict) else None
            if og:
                door_owners.append(og)
            continue
        inner = d.get("details", {})
        beg = inner.get("begCoordinate") or d.get("begCoordinate")
        end = inner.get("endCoordinate") or d.get("endCoordinate")
        if beg and end:
            walls.append((g, (float(beg["x"]), float(beg["y"])),
                          (float(end["x"]), float(end["y"]))))

    comps = _wall_components(walls)
    for ci, comp in enumerate(sorted(comps, key=len, reverse=True)):
        seg_guids = [walls[i][0] for i in comp]
        segments = [(walls[i][1], walls[i][2]) for i in comp]
        if len(segments) < 3:
            print(f"  • walls#{ci + 1}: <3 ścian, pomijam")
            continue
        points = _chain_segments(segments)
        if len(points) < 3:
            print(f"  • walls#{ci + 1}: nie domyka się ({len(points)} pkt), pomijam")
            continue
        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        owner = next((o for o in door_owners if o in seg_guids), None)
        if owner is not None:
            entry, wt = _detect_entry_from_door(points, segments, seg_guids, owner)
        else:
            entry, wt = _detect_entry_and_wall_types(points)
        outlines.append((polygon, entry, wt, f"walls#{ci + 1}"))
    return outlines, "walls→components"


def main():
    print("Multi-obrys eksport do ArchiCAD — łączę (Tapir, 19723-30) ...")
    try:
        from bridge.tapir_connection import TapirConnection
        from bridge.boundary_reader import read_boundary_from_archicad  # noqa: F401 (import sanity)
        from bridge.plan_writer import export_plan_to_archicad
    except Exception as e:
        print(f"BŁĄD importu bridge: {e!r}")
        return

    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}  → ArchiCAD + Tapir włączone?")
        return

    selected = tapir.get_selected_elements()
    if not selected:
        print("Brak zaznaczenia. Zaznacz kilka obrysów (Zone per obrys / Slab / ściany).")
        return
    guids = [_guid(e) for e in selected]
    details = tapir.get_element_details(guids)
    comp = Counter(d.get("type", "?") for d in details if isinstance(d, dict))
    print(f"\nZaznaczenie: {len(guids)} elementów → {dict(comp)}")

    outlines, mode = _collect_outlines(tapir, details, guids)
    print(f"Tryb: {mode}; obrysów do przetworzenia: {len(outlines)}\n")
    if not outlines:
        print("Nic do przetworzenia. Dla wielu obrysów najlepiej: po jednej Zone (Inner Edge) "
              "na obrys, albo Slab-y. Same ściany kilku mieszkań zlepią się w jeden polygon.")
        return

    ok_count = 0
    for polygon, entry, wall_types, label in outlines:
        bx0, by0, bx1, by1 = polygon.bounds
        print(f"=== {label}: bounds=({bx0:.2f},{by0:.2f})..({bx1:.2f},{by1:.2f}) "
              f"{bx1 - bx0:.1f}×{by1 - by0:.1f} m, pole={polygon.area:.1f} m² ===")
        offset = (bx0, by0)
        shifted = translate(polygon, -bx0, -by0)
        entry_shifted = (entry[0] - bx0, entry[1] - by0)

        plan = used = None
        for mtype in MTYPE_FALLBACK:
            try:
                plans = generate_variants(shifted, entry_shifted, mtype,
                                          max_variants=1, wall_types=wall_types)
            except Exception as e:
                print(f"  {mtype}: błąd solvera ({e})")
                continue
            if plans:
                plan, used = plans[0], mtype
                break
        if plan is None:
            print(f"  → POMINIĘTY: żaden typ M nie zmieścił się ({polygon.area:.1f} m²)\n")
            continue
        print(f"  {used}: {len(plan.rooms)} pokoi (template {plan.template.id})")

        try:
            result = export_plan_to_archicad(plan, tapir=tapir, offset=offset,
                                             include_furniture=True)
        except Exception as e:
            import traceback
            print(f"  → BŁĄD eksportu: {e!r}")
            traceback.print_exc()
            continue
        counts = {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}
        print(f"  → wstawiono: {counts}\n")
        ok_count += 1

    print(f"GOTOWE: {ok_count}/{len(outlines)} obrysów wyeksportowanych. "
          "Sprawdź w AC — meble powinny stać PRZY ścianach, a aneks dziennego mieć blat.")


if __name__ == "__main__":
    main()
