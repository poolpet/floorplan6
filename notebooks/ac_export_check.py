"""De-risk integracji REALNYM flow: wczytaj ZAZNACZONY obrys z ArchiCAD,
wygeneruj rozkład pokoi i wyeksportuj go z powrotem DOKŁADNIE w ten obrys.

To jest 1:1 ścieżka produktu (jak przycisk "import z AC" + "generuj" + "do AC"
w GUI), więc de-risk bada właściwą rzecz:
    read_boundary (world) → shift do (0,0) → generate_variants →
    export_plan_to_archicad(offset = róg świata) → pokoje lądują w Twoim obrysie.

Dlaczego shift+offset: solver liczy w lokalnych (0..w, 0..h), a Twoje ściany
obwodowe są w world coords. Offset = (bx0, by0) wraca pokoje na Twój obrys,
którego ściany JUŻ istnieją w AC → strefy się domykają, okna trafiają w fasadę.

Uruchom z włączonym ArchiCAD + Tapir, MAJĄC ZAZNACZONE ściany obrysu mieszkania
(razem z drzwiami wejściowymi — wykryją wejście):
    PYTHONPATH=. venv/bin/python notebooks/ac_export_check.py

Drukuje: odczytany obrys (bounds/pole), użyty typ M, liczniki wstawionych
stref/ścian/drzwi/okien (GUID-y) lub błąd.
"""
from shapely.affinity import translate

from core.variant_generator import generate_variants

# Kolejność prób typu mieszkania — pierwszy feasible dla danego obrysu wygrywa.
MTYPE_FALLBACK = ["M3", "M2", "M4", "M1", "M5"]


def main():
    print("Łączę z ArchiCAD (Tapir, porty 19723-19730) ...")
    try:
        from bridge.tapir_connection import TapirConnection
        from bridge.boundary_reader import read_boundary_from_archicad
        from bridge.plan_writer import export_plan_to_archicad
    except Exception as e:
        print(f"BŁĄD importu bridge: {e!r}")
        return

    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia z ArchiCAD: {e!r}")
        print("  → Czy ArchiCAD działa? Czy Tapir add-on jest zainstalowany i włączony?")
        return

    print("\nCzytam ZAZNACZONY obrys z ArchiCAD ...")
    try:
        polygon, entry_point, wall_types = read_boundary_from_archicad(tapir)
    except Exception as e:
        print(f"BŁĄD odczytu obrysu: {e!r}")
        print("  → Zaznacz w AC ściany obrysu mieszkania (+ drzwi wejściowe) i spróbuj ponownie.")
        return

    bx0, by0, bx1, by1 = polygon.bounds
    print(f"  OK — obrys bounds=({bx0:.2f},{by0:.2f})..({bx1:.2f},{by1:.2f}), "
          f"{bx1 - bx0:.2f}×{by1 - by0:.2f} m, pole={polygon.area:.1f} m², "
          f"wejście=({entry_point[0]:.2f},{entry_point[1]:.2f})")

    # Shift do origin (solver liczy lokalnie), offset wraca na Twój obrys.
    offset = (bx0, by0)
    shifted = translate(polygon, -bx0, -by0)
    entry_shifted = (entry_point[0] - bx0, entry_point[1] - by0)

    print("\nGeneruję rozkład pokoi (real flow) ...")
    plan = None
    used_mtype = None
    for mtype in MTYPE_FALLBACK:
        plans = generate_variants(
            shifted, entry_shifted, mtype, max_variants=1,
            wall_types=wall_types,
        )
        if plans:
            plan, used_mtype = plans[0], mtype
            break
        print(f"  {mtype}: brak wariantu (INFEASIBLE dla tego obrysu) — próbuję dalej")

    if plan is None:
        print("BŁĄD: żaden typ mieszkania nie zmieścił się w tym obrysie "
              f"({polygon.area:.1f} m²). Spróbuj większego/innego obrysu.")
        return
    print(f"  OK — {used_mtype}, {len(plan.rooms)} pokoi, template {plan.template.id}")

    print("\nEksportuję do ArchiCAD (offset = róg obrysu → pokoje w Twoim obrysie) ...")
    try:
        result = export_plan_to_archicad(plan, tapir=tapir, offset=offset)
    except Exception as e:
        import traceback
        print(f"BŁĄD eksportu: {e!r}")
        traceback.print_exc()
        return

    print("\n=== WYNIK ===")
    for key, guids in result.items():
        n = len(guids) if isinstance(guids, list) else guids
        print(f"  {key:12s}: {n}")
    print("\nSprawdź w ArchiCAD: strefy pokoi POWINNY wypełnić Twój zaznaczony obrys "
          "(zamknięte, bez 'nie zamknięty'), ścianki działowe wewnątrz, drzwi (łuki), "
          "okna na ścianach fasady.")


if __name__ == "__main__":
    main()
