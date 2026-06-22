"""SELF-TEST (uruchamia Claude): kuchnia z pojedynczych mebli — pełna ścieżka end-to-end.
Buduje przykładowy blat (kitchen_counter box 2.4×0.6), przepuszcza przez
extract_furniture (rozbicie na lodówkę+szafki) → CreateObjects → SetGDLParameters A/B,
i ODCZYTUJE z AC nazwy+wymiary+pozycje, żeby potwierdzić: rząd modułów 0.6 w linii,
1 Lodówka + N Szafek podstawowych, realny rozmiar.

    PYTHONPATH=. venv/bin/python notebooks/ac_kitchenette_check.py
"""
from __future__ import annotations

from shapely.geometry import box

from core.furniture import Furniture, FurnishResult
from core.furniture_extractor import (
    extract_furniture, furniture_to_create_payload, furniture_to_gdl_payload,
)

# Blat 2.4×0.6 daleko od geometrii (poziomy bieg) — oczekiwane 4 moduły: lodówka + 3 szafki.
ORIGIN = (5.0, -20.0)
COUNTER = box(ORIGIN[0], ORIGIN[1], ORIGIN[0] + 2.4, ORIGIN[1] + 0.6)


def main():
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    tapir.connect()
    print(f"Połączono port {tapir.active_port}")

    f = Furniture("kitchen_counter", COUNTER, "salon_aneks", "Blat")
    objs = extract_furniture(FurnishResult([f], []), [])
    print(f"\nextract_furniture → {len(objs)} obiektów:")
    for o in objs:
        print(f"  {o.library_part_name:22s} kotwica=({o.x:.2f},{o.y:.2f}) A×B={o.dim_x}×{o.dim_y}")

    create = furniture_to_create_payload(objs)
    guids = tapir.create_objects(create)
    print(f"\nCreateObjects → {len(guids)}/{len(objs)} guidów")
    gdl = furniture_to_gdl_payload(objs, guids)
    if gdl:
        res = tapir.set_gdl_parameters(gdl)
        oks = sum(1 for r in res.get("executionResults", []) if isinstance(r, dict) and r.get("success"))
        print(f"SetGDLParameters → success {oks}/{len(gdl)}")

    print("\nODCZYT z AC (co faktycznie stanęło — w tym wyposażenie):")
    for g in guids:
        det = tapir.get_element_details([g])
        inner = det[0].get("details", det[0]) if det else {}
        lib = inner.get("libPart", {})
        name = lib.get("name") if isinstance(lib, dict) else "?"
        origin = inner.get("origin", {})
        dims = inner.get("dimensions", {})
        # odczyt wyposażenia
        pr = tapir._execute_tapir("GetGDLParametersOfElements",
                                  {"elements": [{"elementId": {"guid": g}}]})
        plist = (pr.get("gdlParametersOfElements", [{}]) or [{}])[0]
        pmap = {p.get("name"): p.get("value") for p in
                (plist.get("parameters", []) if isinstance(plist, dict) else plist)
                if isinstance(p, dict)}
        equip = ""
        if name == "Szafka podstawowa":
            tags = [t for t, k in (("ZLEW", "bSink"), ("PŁYTA", "bCooktop"), ("blat", "bCounter"))
                    if pmap.get(k)]
            equip = " [" + (", ".join(tags) if tags else "pusta") + "]"
        print(f"  {name:22s} origin=({origin.get('x'):.2f},{origin.get('y'):.2f}) "
              f"dims=({dims.get('x')},{dims.get('y')}){equip}")
    n = tapir.delete_elements(guids)
    print(f"sprzątanie: delete zwrócił {n} (mogą zostać — wyczyść ac_clean_and_export).")


if __name__ == "__main__":
    main()
