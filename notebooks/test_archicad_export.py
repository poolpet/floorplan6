"""
Eksport wariantu 1 do ArchiCAD jako strefy.

Powtarza odczyt obrysu + generowanie + eksport do AC.
Strefy wstawiane w globalnych współrzędnych AC (offset=0,0) — bezpośrednio na obrysie.

UWAGA: po eksporcie w AC pojawi się N stref (N = liczba pokoi). Przed kolejnym
uruchomieniem usuń poprzednie strefy w AC, inaczej będzie duplikat.
"""
import sys


def main(mtype: str = "M3"):
    from bridge.tapir_connection import TapirConnection
    from bridge.boundary_reader import read_boundary_from_archicad
    from bridge.plan_writer import export_plan_to_archicad
    from core.variant_generator import generate_variants

    print("=== Eksport wariantu 1 do ArchiCAD ===\n")

    print("[1/4] Łączenie z ArchiCAD...")
    tapir = TapirConnection()
    tapir.connect()
    print("    ✓ Połączono\n")

    print("[2/4] Odczyt obrysu...")
    selected = tapir.get_selected_elements()
    if not selected:
        print("    ✗ Brak zaznaczonych ścian!")
        sys.exit(1)
    polygon, entry_point, wall_types = read_boundary_from_archicad(tapir)
    print(f"    ✓ Obrys {polygon.area:.2f}m², bbox {polygon.bounds}\n")

    print(f"[3/4] Generowanie wariantu {mtype}...")
    variants = generate_variants(
        polygon=polygon, entry_point=entry_point, mtype=mtype, max_variants=3,
    )
    if not variants:
        print("    ✗ Brak wariantów")
        sys.exit(1)
    best = variants[0]
    print(f"    ✓ Wariant 1: score={best.score:.3f} (template={best.template.id})")
    for room in sorted(best.rooms, key=lambda r: -r.area):
        print(f"      {room.spec.nazwa:30s} {room.area:5.1f}m²")
    print()

    print("[4/4] Eksport do AC (Zones + Walls + Doors + Openings, offset=0,0)...")
    result = export_plan_to_archicad(best, tapir=tapir, offset=(0.0, 0.0))
    zone_guids = result["zones"]
    wall_guids = result["walls"]
    door_guids = result["doors"]
    opening_guids = result.get("openings", [])
    print(f"    ✓ Utworzono {len(zone_guids)} stref + {len(wall_guids)} ścianek + "
          f"{len(door_guids)} drzwi + {len(opening_guids)} otworów w AC")

    print("\n=== KONIEC ===")
    print("Strefy widoczne w AC. Jeśli nie widzisz — sprawdź View → Layers → Zone visible.")


if __name__ == "__main__":
    mtype = sys.argv[1] if len(sys.argv) > 1 else "M3"
    main(mtype)
