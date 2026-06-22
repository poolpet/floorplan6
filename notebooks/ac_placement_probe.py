"""DIAGNOSTYKA KOTWICZENIA (uruchamia Claude): stawia kluczowe meble w znanych punktach
+ MARKER (mały slab) DOKŁADNIE w punkcie wstawienia każdego. Z zrzutu widać, gdzie obiekt
rysuje się względem swojego origin (lewy-dolny róg? środek? inny?) — to przesądza jak
naprawić lokalizację wszystkich mebli.

Każdy mebel w (i*STEP, Y); marker = slab 0.14×0.14 wyśrodkowany na TYM SAMYM punkcie.
Obiekt + A/B przez naszą produkcyjną ścieżkę (CreateObjects + SetGDLParameters).

    PYTHONPATH=. venv/bin/python notebooks/ac_placement_probe.py
Potem: zrzut okolicy (y≈-30, x≈0..28) → przyślij; policzę offsety.
"""
from __future__ import annotations

# (nazwa biblioteczna, A, B) — realne wymiary jak w mapie
TESTS = [
    ("Łóżko podwójne 01", 1.8, 2.0),
    ("Sofa", 1.6, 0.85),
    ("Garderoba 01", 1.2, 0.6),
    ("Szafka RTV wisząca", 1.8, 0.4),
    ("Szafka podstawowa", 0.6, 0.58),
    ("Lodówka", 0.6, 0.6),
    ("WC", 0.35, 0.64),
    ("Stół jadalniany prostokątny", 2.6, 1.8),
]
Y = -30.0
STEP = 3.5
MARK = 0.07  # pół-bok markera


def _marker_slab(x, y):
    return {"level": 0.0, "thickness": 0.05,
            "polygonCoordinates": [
                {"x": x - MARK, "y": y - MARK}, {"x": x + MARK, "y": y - MARK},
                {"x": x + MARK, "y": y + MARK}, {"x": x - MARK, "y": y + MARK}]}


def main():
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    tapir.connect()
    print(f"Połączono port {tapir.active_port}\n")

    markers = []
    for i, (name, A, B) in enumerate(TESTS):
        x = i * STEP
        g = tapir.create_objects([{"libraryPartName": name,
                                   "coordinates": {"x": x, "y": Y, "z": 0.0}}])
        if not g:
            print(f"  ✗ '{name}' nie wstawiony")
            continue
        tapir.set_gdl_parameters([{"elementId": {"guid": g[0]},
                                   "gdlParameters": [{"name": "A", "value": A},
                                                     {"name": "B", "value": B}]}])
        # marker w punkcie wstawienia
        try:
            tapir._execute_tapir("CreateSlabs", {"slabsData": [_marker_slab(x, Y)]})
            mk = "marker✓"
        except Exception as e:  # noqa: BLE001
            mk = f"marker✗({str(e)[:40]})"
            markers.append(False)
        print(f"  [{i}] '{name}' w punkcie ({x:.1f},{Y})  A×B={A}×{B}  {mk}")

    print(f"\nGotowe. Zrzut okolicy y≈{Y}, x≈0..{(len(TESTS)-1)*STEP:.0f} → przyślij.")
    print("Dla każdego: gdzie jest mebel względem małego kwadratu-markera w jego punkcie?")
    print("(środek? lewy-dolny róg? inny?) — z tego naprawię lokalizację wszystkich mebli.")


if __name__ == "__main__":
    main()
