"""SMOKE TEST DOMU → ArchiCAD (S31b).

Cel: zdjąć ryzyko, czy DOM jednorodzinny (inny zestaw pokoi niż mieszkanie + pokój
'schody') round-trippuje do AC tak jak potwierdzona ścieżka mieszkań. Test = ŚCIANY +
nazwane STREFY (pokoje) PARTERU. BEZ drzwi (template-based), okien, mebli (Tapir-frozen),
labeli — najczystsza geometria.

Mirror `ac_clean_and_export.py`, ale: generate_house zamiast generate_variants, eksport
parteru jako FloorPlan(template=None).

URUCHOM z otwartym AC + Tapir, MAJĄC ZAZNACZONY jeden obrys (ściany prostokąta, np. 10×8 m):
    PYTHONPATH=. venv/bin/python notebooks/ac_house_smoke.py
"""
from __future__ import annotations

from shapely.affinity import translate

from core.house_layout import generate_house
from core.models import FloorPlan
from notebooks.ac_export_multi import _collect_outlines, _guid


def main():
    print("SMOKE DOMU → AC — łączę z ArchiCAD ...")
    from bridge.tapir_connection import TapirConnection
    from bridge.plan_writer import export_plan_to_archicad
    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}  (czy AC + Tapir działają?)")
        return

    # 1) Odczytaj zaznaczony obrys (ściany prostokąta) — Twój input, jak w ścieżce mieszkań.
    selected = tapir.get_selected_elements()
    keep = [_guid(e) for e in selected]
    if not keep:
        print("Brak zaznaczenia — zaznacz ŚCIANY jednego obrysu (np. prostokąt 10×8 m) i powtórz.")
        return
    details = tapir.get_element_details(keep)
    outlines, mode = _collect_outlines(tapir, details, keep)
    print(f"  Zaznaczenie: {len(keep)} elem; tryb={mode}; obrysów policzonych: {len(outlines)}")
    if not outlines:
        print("  Nie policzyłem obrysu z zaznaczenia — przerywam.")
        return

    polygon, entry, _wall_types, label = outlines[0]
    bx0, by0, bx1, by1 = polygon.bounds
    W, H = bx1 - bx0, by1 - by0
    print(f"  Obrys '{label}': {W:.2f}×{H:.2f} m = {polygon.area:.1f} m², wejście ~{entry}")

    # 2) Generuj DOM na tym obrysie (local frame: przesuń do (0,0)).
    shifted = translate(polygon, -bx0, -by0)
    entry_s = (entry[0] - bx0, entry[1] - by0)
    # Adaptywnie: ≥65 m² → dom 2-kond.; mniej → parterowiec (1-kond.). Fallback: gdy
    # 2-kond. = loteria perf parteru, spróbuj parterowca (niezawodny) — smoke testuje
    # PIPE AC, nie perf solvera, więc byle dom się wygenerował.
    n0 = 2 if polygon.area >= 65.0 else 1
    print(f"  generate_house ({n0}-kond.) — solver CP-SAT, ~30-90 s ...")
    layout = generate_house(shifted, entry_point=entry_s, num_storeys=n0, time_limit_s=90.0)
    if not layout.ok and n0 == 2:
        print(f"  2-kond. nie wyszło ({layout.message[:50]}) — fallback parterowiec (1-kond.) ...")
        layout = generate_house(shifted, entry_point=entry_s, num_storeys=1, time_limit_s=90.0)
    if not layout.ok:
        print(f"  generate_house NIE OK: {layout.message}  — spróbuj obrysu ~9×8 m (compact).")
        return
    print(f"  Dom OK ({'parterowiec' if not layout.pietro_rooms else '2-kond.'}). "
          f"stair_kind={layout.stair_kind}. Parter: {[r.spec.nazwa for r in layout.parter_rooms]}")

    # 3) Eksport PARTERU jako strefy + ścianki działowe (bez drzwi/okien/mebli/labeli).
    plan = FloorPlan(boundary=layout.boundary, template=None, rooms=layout.parter_rooms)
    try:
        res = export_plan_to_archicad(
            plan, tapir=tapir, offset=(bx0, by0),
            include_walls=True, include_doors=False, include_labels=False,
            include_windows=False, include_furniture=False,
            apartment_id="DOM-PARTER",
        )
    except Exception as e:
        print(f"  BŁĄD eksportu parteru: {e!r}")
        return

    counts = {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}
    print(f"\nGOTOWE — PARTER domu w AC: {counts}")
    print("  Sprawdź w ArchiCAD: nazwane strefy (Salon/Kuchnia/Hol/Schody/Łazienka/Sypialnia…)")
    print("  + ścianki działowe między nimi, wewnątrz Twojego obrysu.")
    print("  (drzwi/okna/meble świadomie pominięte — test geometrii pokoi+ścian domu.)")


if __name__ == "__main__":
    main()
