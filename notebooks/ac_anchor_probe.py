"""PROBE kotwicy CreateObjects: czy `coordinates{x,y}` to LEWY-DOLNY RÓG czy ŚRODEK?

Cały eksport mebli zakłada „kotwica = lewy-dolny róg boxa" (core/furniture_extractor.py:49),
ale to założenie jest TYLKO w komentarzu — źródło `_probe_roundtrip` NIE istnieje i nie ma
odczytu po wstawieniu. Jeśli AC kotwiczy obiekt w ŚRODKU (albo w origin części), KAŻDY mebel
jest przesunięty o ~pół wymiaru — jednolite „pływanie" NA WIERZCHU bugu osi (już naprawionego).

Ten probe rozstrzyga to empirycznie: wstawia znane obiekty w PUSTEJ przestrzeni (obiekty
biblioteczne NIE wymagają ścian — brak artefaktu „pustki w origin"), odczytuje ich pozycję
(GetDetailsOfElements) i porównuje z wysłaną współrzędną. Dodatkowo sprawdza H3: czy
nieistniejąca część jest po cichu pomijana (zero GUID, brak błędu).

Uruchom z włączonym ArchiCAD + Tapir (nie trzeba nic zaznaczać):
    PYTHONPATH=. venv/bin/python notebooks/ac_anchor_probe.py

Po uruchomieniu: wklej mi wydruk — z surowego odczytu jednoznacznie wynika róg vs środek.
"""
from __future__ import annotations

import json

from core.furniture_extractor import BED_DOUBLE

# Wstawiamy daleko od origin/istniejącej geometrii, by łatwo znaleźć i bez kolizji.
PROBES = [
    {"libraryPartName": "Sofa",
     "coordinates": {"x": 10.0, "y": 10.0, "z": 0.0},
     "dimensions": {"x": 1.6, "y": 0.85}},
    {"libraryPartName": BED_DOUBLE,
     "coordinates": {"x": 14.0, "y": 10.0, "z": 0.0},
     "dimensions": {"x": 1.8, "y": 2.0}},
]
BOGUS = {"libraryPartName": "___PROBE_NIE_ISTNIEJE___",
         "coordinates": {"x": 18.0, "y": 10.0, "z": 0.0},
         "dimensions": {"x": 1.0, "y": 1.0}}


def _find_xy_pairs(node, path="root"):
    """Rekurencyjnie znajdź wszystkie dict-y z liczbowymi x,y (lub xMin,yMin)."""
    out = []
    if isinstance(node, dict):
        if "x" in node and "y" in node and isinstance(node.get("x"), (int, float)):
            out.append((path, "point", float(node["x"]), float(node["y"])))
        if "xMin" in node and "yMin" in node:
            out.append((path + ".bbox", "bbox",
                        float(node["xMin"]), float(node["yMin"]),
                        float(node.get("xMax", node["xMin"])), float(node.get("yMax", node["yMin"]))))
        for k, v in node.items():
            out += _find_xy_pairs(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _find_xy_pairs(v, f"{path}[{i}]")
    return out


def _interpret(sent: dict, detail: dict):
    sx, sy = sent["coordinates"]["x"], sent["coordinates"]["y"]
    dx, dy = sent["dimensions"]["x"], sent["dimensions"]["y"]
    cx, cy = sx + dx / 2, sy + dy / 2   # gdyby (sx,sy) był ROGIEM → środek tu
    print(f"  wysłano: róg=({sx},{sy}) wymiary=({dx},{dy}) → środek-jeśli-róg=({cx:.2f},{cy:.2f})")
    pairs = _find_xy_pairs(detail)
    if not pairs:
        print("  (brak rozpoznawalnych x/y w odczycie — patrz surowy JSON wyżej)")
        return
    for p in pairs:
        if p[1] == "point":
            _, _, x, y = p
            tag = []
            if abs(x - sx) < 0.02 and abs(y - sy) < 0.02:
                tag.append("== WYSŁANY RÓG (kotwica=róg ✓)")
            if abs(x - cx) < 0.02 and abs(y - cy) < 0.02:
                tag.append("== ŚRODEK (kotwica=ŚRODEK! trzeba emitować centroid)")
            print(f"  {p[0]}: point=({x:.3f},{y:.3f}) {' '.join(tag)}")
        else:
            _, _, xmin, ymin, xmax, ymax = p
            bx, by = (xmin + xmax) / 2, (ymin + ymax) / 2
            tag = []
            if abs(xmin - sx) < 0.05 and abs(ymin - sy) < 0.05:
                tag.append("min==WYSŁANY RÓG (kotwica=róg ✓)")
            if abs(bx - sx) < 0.05 and abs(by - sy) < 0.05:
                tag.append("środek-bbox==WYSŁANY (kotwica=ŚRODEK!)")
            print(f"  {p[0]}: bbox=({xmin:.2f},{ymin:.2f})..({xmax:.2f},{ymax:.2f}) "
                  f"środek=({bx:.2f},{by:.2f}) {' '.join(tag)}")


def main():
    print("PROBE kotwicy CreateObjects (róg vs środek) — łączę z ArchiCAD ...")
    try:
        from bridge.tapir_connection import TapirConnection
    except Exception as e:
        print(f"BŁĄD importu bridge: {e!r}")
        return
    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}\n")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}  → ArchiCAD + Tapir włączone?")
        return

    print(f"Wstawiam {len(PROBES)} znane obiekty (Sofa, {BED_DOUBLE}) w (10,10)/(14,10) ...")
    try:
        guids = tapir.create_objects(PROBES)
    except Exception as e:
        import traceback
        print(f"BŁĄD create_objects: {e!r}")
        traceback.print_exc()
        return
    print(f"  → wstawiono {len(guids)}/{len(PROBES)} GUID-ów: {guids}\n")
    if not guids:
        print("  Żaden obiekt się nie wstawił — nazwy części mogą się nie zgadzać z biblioteką.")
        return

    details = tapir.get_element_details(guids)
    for i, (sent, guid) in enumerate(zip(PROBES, guids)):
        d = details[i] if i < len(details) else {}
        print(f"=== obiekt {i}: {sent['libraryPartName']} (guid {guid}) ===")
        print("  --- surowy GetDetailsOfElements ---")
        print("  " + json.dumps(d, indent=2, ensure_ascii=False).replace("\n", "\n  "))
        print("  --- interpretacja ---")
        _interpret(sent, d)
        print()

    # H3: czy nieistniejąca część jest po cichu pomijana?
    print("Test H3 — wstawiam NIEISTNIEJĄCĄ część (oczekiwane: 0 GUID, brak błędu) ...")
    try:
        bog = tapir.create_objects([BOGUS])
        print(f"  → {len(bog)} GUID. {'0 = po cichu pominięte → H3 POTWIERDZONE' if not bog else 'utworzono (?!)'}")
    except Exception as e:
        print(f"  create_objects rzucił wyjątek (a NIE po cichu): {e!r}")

    print("\nGotowe. Wklej mi powyższy wydruk — rozstrzygniemy róg vs środek i ew. poprawimy payload.")
    print("(Wstawione obiekty probe możesz skasować w AC — stoją w (10,10)/(14,10).)")


if __name__ == "__main__":
    main()
