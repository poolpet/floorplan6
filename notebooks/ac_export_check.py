"""De-risk integracji: wygeneruj mieszkanie M3 i wyeksportuj do ArchiCAD przez Tapir.

Uruchom z włączonym ArchiCAD + Tapir (custom build) na porcie 19723-19730:
    PYTHONPATH=. venv/bin/python notebooks/ac_export_check.py

Drukuje: stan połączenia, ile stref/ścian/drzwi/okien wstawiono (GUID-y) lub błąd.
Cel: potwierdzić, że pipe mieszkanie→AC działa na tej maszynie, ZANIM dobudujemy meble→AC.
"""
from shapely.geometry import Polygon

from core.variant_generator import generate_variants


def main():
    poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
    print("Generuję mieszkanie M3 10×8 ...")
    plans = generate_variants(poly, (5.0, 0.0), "M3", max_variants=1)
    if not plans:
        print("BŁĄD: generator nie zwrócił żadnego wariantu")
        return
    plan = plans[0]
    print(f"  OK — {len(plan.rooms)} pokoi, template {plan.template.id}")

    print("\nŁączę z ArchiCAD (Tapir, porty 19723-19730) ...")
    try:
        from bridge.tapir_connection import TapirConnection
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

    print("\nEksportuję do ArchiCAD (strefy + ścianki + drzwi + okna + etykiety) ...")
    try:
        result = export_plan_to_archicad(plan, tapir=tapir)
    except Exception as e:
        import traceback
        print(f"BŁĄD eksportu: {e!r}")
        traceback.print_exc()
        return

    print("\n=== WYNIK ===")
    for key, guids in result.items():
        n = len(guids) if isinstance(guids, list) else guids
        print(f"  {key:12s}: {n}")
    print("\nSprawdź w ArchiCAD czy pojawiły się: strefy pokoi, ścianki, drzwi (łuki), okna na fasadzie.")


if __name__ == "__main__":
    main()
