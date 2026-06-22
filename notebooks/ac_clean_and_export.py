"""Jednorazowe: WYCZYŚĆ wygenerowane śmieci z dokumentu AC (z ~100 poprzednich runów)
i zrób JEDEN czysty eksport 4 zaznaczonych obrysów. ZACHOWUJE zaznaczone ściany
obrysów + drzwi (Twój input), kasuje resztę (strefy/obiekty/okna/wygenerowane ścianki/drzwi).

Kolejność jest ważna: NAJPIERW liczymy obrysy z zaznaczenia (dopóki istnieje), POTEM
kasujemy, POTEM eksportujemy z zapamiętanych obrysów (nie zależymy od zaznaczenia po delete).

Uruchom z AC + Tapir, MAJĄC ZAZNACZONE ściany obrysów (+ drzwi wejściowe):
    PYTHONPATH=. venv/bin/python notebooks/ac_clean_and_export.py
"""
from __future__ import annotations

from shapely.affinity import translate

from core.variant_generator import generate_variants
from notebooks.ac_export_multi import _collect_outlines, _guid

MTYPE_FALLBACK = ["M3", "M2", "M4", "M1", "M5"]
KEEP_TYPES = ("Wall", "Door")            # te zachowujemy jeśli zaznaczone (obrysy)
PURGE_ALL_TYPES = ("Zone", "Object", "Window", "Slab")  # te kasujemy w całości (Slab = markery sond)
BATCH = 150


def _all_guids(tapir, typ):
    return [_guid(e) for e in tapir.get_elements_by_type(typ)]


def main():
    print("CLEAN + czysty eksport — łączę z AC ...")
    from bridge.tapir_connection import TapirConnection
    from bridge.plan_writer import export_plan_to_archicad
    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}")
        return

    # 1) Policz obrysy z zaznaczenia ZANIM skasujemy + zapamiętaj GUID-y do ZACHOWANIA.
    selected = tapir.get_selected_elements()
    keep = {_guid(e) for e in selected}
    if not keep:
        print("Brak zaznaczenia — zaznacz ściany obrysów (+drzwi) i powtórz.")
        return
    details = tapir.get_element_details(list(keep))
    outlines, mode = _collect_outlines(tapir, details, list(keep))
    print(f"  Zaznaczenie: {len(keep)} elem; tryb={mode}; obrysów policzonych: {len(outlines)}")
    if not outlines:
        print("  Nie policzyłem obrysów — przerywam (nic nie kasuję).")
        return

    # 2) Zbierz wszystko do skasowania (zachowując `keep`).
    to_delete = []
    for typ in PURGE_ALL_TYPES:
        to_delete += _all_guids(tapir, typ)
    for typ in KEEP_TYPES:
        to_delete += [g for g in _all_guids(tapir, typ) if g not in keep]
    to_delete = [g for g in dict.fromkeys(to_delete) if g and g not in keep]
    print(f"  Do skasowania: {len(to_delete)} wygenerowanych elementów (zachowuję {len(keep)}).")

    deleted = 0
    for i in range(0, len(to_delete), BATCH):
        chunk = to_delete[i:i + BATCH]
        try:
            tapir.delete_elements(chunk)
            deleted += len(chunk)
        except Exception as e:
            print(f"  • batch {i//BATCH}: błąd kasowania ({e})")
    print(f"  Skasowano ~{deleted}. Stan po: "
          f"Zone={len(_all_guids(tapir,'Zone'))}, Object={len(_all_guids(tapir,'Object'))}, "
          f"Wall={len(_all_guids(tapir,'Wall'))}, Window={len(_all_guids(tapir,'Window'))}, "
          f"Door={len(_all_guids(tapir,'Door'))}\n")

    # 3) Czysty eksport zapamiętanych obrysów.
    ok = 0
    for polygon, entry, wall_types, label in outlines:
        bx0, by0, bx1, by1 = polygon.bounds
        offset = (bx0, by0)
        shifted = translate(polygon, -bx0, -by0)
        entry_s = (entry[0] - bx0, entry[1] - by0)
        plan = used = None
        for mtype in MTYPE_FALLBACK:
            try:
                plans = generate_variants(shifted, entry_s, mtype, max_variants=1, wall_types=wall_types)
            except Exception as e:
                print(f"  {label} {mtype}: {e}")
                continue
            if plans:
                plan, used = plans[0], mtype
                break
        if plan is None:
            print(f"  {label} ({polygon.area:.1f} m²): POMINIĘTY (INFEASIBLE)")
            continue
        res = None
        for attempt in range(3):   # retry na transient 'ongoing user input' (klik w AC)
            try:
                res = export_plan_to_archicad(plan, tapir=tapir, offset=offset, include_furniture=True)
                break
            except Exception as e:
                if "user input" in str(e) and attempt < 2:
                    print(f"  {label}: AC zajęte (próba {attempt+1}/3) — czekam, NIE klikaj w AC ...")
                    import time; time.sleep(3)
                    continue
                print(f"  {label}: BŁĄD eksportu ({e})")
                break
        if res is None:
            continue
        counts = {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}
        print(f"  {label} → {used} ({polygon.area:.1f} m²): {counts}")
        ok += 1

    print(f"\nGOTOWE: dokument wyczyszczony + {ok}/{len(outlines)} mieszkań wyeksportowanych na czysto.")
    print("Sprawdź w AC — teraz bez nakładek: meble przy ścianach, kuchnia w aneksie, stoliki w środku.")


if __name__ == "__main__":
    main()
