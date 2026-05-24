"""
Test integracji z ArchiCAD.

Użycie:
  1. Zaznacz ściany obrysu mieszkania w ArchiCAD
  2. Uruchom: python run_archicad.py
  3. Podaj typ (M1/M2/M3) i ścianę z drzwiami

Alternatywnie bez ArchiCAD — ręczne wymiary:
  python run_archicad.py --manual --type M2 --width 7 --height 9
"""
import argparse
import sys
from pathlib import Path

from shapely.geometry import Polygon


def run_from_archicad(mtype: str):
    """Odczytaj obrys z ArchiCAD, wygeneruj rzut, wyeksportuj strefy."""
    from bridge.tapir_connection import TapirConnection
    from bridge.boundary_reader import read_boundary_from_archicad
    from bridge.plan_writer import export_plan_to_archicad
    from core.boundary_analyzer import analyze_boundary
    from core.variant_generator import generate_variants
    from viz.plan_renderer import render_floor_plan

    print("Łączę z ArchiCAD...")
    tapir = TapirConnection()
    tapir.connect()
    print("✓ Połączono z ArchiCAD")

    print("\nOdczytuję zaznaczone ściany...")
    polygon, entry_point, wall_types = read_boundary_from_archicad(tapir)
    print(f"✓ Obrys: {polygon.bounds}")
    print(f"  Powierzchnia: {polygon.area:.1f} m²")
    print(f"  Entry point: ({entry_point[0]:.2f}, {entry_point[1]:.2f})")

    # Analiza i generowanie
    boundary = analyze_boundary(polygon, entry_point, wall_types)
    print(f"  Fasady: {len(boundary.facade_edges)}, Internal: {len(boundary.internal_edges)}")

    print(f"\nGeneruję warianty {mtype}...")
    variants = generate_variants(
        polygon=polygon,
        entry_point=entry_point,
        mtype=mtype,
        max_variants=3,
    )

    if not variants:
        print("❌ Nie wygenerowano żadnego wariantu!")
        sys.exit(1)

    print(f"✓ {len(variants)} wariantów\n")

    # Wyświetl wyniki
    for i, plan in enumerate(variants):
        status = "OK" if plan.is_valid else f"BŁĘDY: {len(plan.validation_errors)}"
        print(f"Wariant {i+1}: score={plan.score:.3f} [{status}]")
        for room in plan.rooms:
            print(f"  {room.spec.nazwa:30s} {room.area:5.1f} m²  "
                  f"({room.width:.2f}×{room.depth:.2f}m)")
        hub = plan.hub_room
        if hub:
            print(f"  Hub: {hub.area:.1f}m² ({plan.hub_percent*100:.1f}%)")
        print()

    # Zapisz najlepszy jako PNG
    best = variants[0]
    out = Path(f"archicad_{mtype}.png")
    render_floor_plan(best, save_path=out, show=False,
                      title=f"ArchiCAD {mtype} — score: {best.score:.3f}")
    print(f"Render: {out}")

    # Eksport do ArchiCAD
    answer = input("\nWyeksportować strefy do ArchiCAD? (t/n): ").strip().lower()
    if answer == "t":
        print("Eksportuję strefy...")
        result = export_plan_to_archicad(best, tapir)
        print(f"✓ Utworzono {len(result['zones'])} stref + "
              f"{len(result['walls'])} ścianek + "
              f"{len(result['doors'])} drzwi + "
              f"{len(result.get('labels', []))} etykiet w ArchiCAD")
    else:
        print("Pominięto eksport.")


def run_manual(mtype: str, width: float, height: float):
    """Generuj rzut z ręcznie podanych wymiarów (bez ArchiCAD)."""
    from core.variant_generator import generate_variants
    from viz.plan_renderer import render_floor_plan

    polygon = Polygon([(0, 0), (width, 0), (width, height), (0, height)])
    entry = (width / 2, 0)

    print(f"Generuję {mtype} dla obrysu {width}×{height}m...")
    variants = generate_variants(polygon, entry, mtype, max_variants=3)

    if not variants:
        print("❌ Brak wariantów!")
        sys.exit(1)

    best = variants[0]
    print(f"\nNajlepszy wariant: score={best.score:.3f}")
    for room in best.rooms:
        print(f"  {room.spec.nazwa:30s} {room.area:5.1f} m²")

    hub = best.hub_room
    if hub:
        print(f"  Hub: {hub.area:.1f}m² ({best.hub_percent*100:.1f}%)")

    out = Path(f"manual_{mtype}_{width}x{height}.png")
    render_floor_plan(best, save_path=out, show=True,
                      title=f"{mtype} {width}×{height}m — score: {best.score:.3f}")
    print(f"Render: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true", help="Bez ArchiCAD, ręczne wymiary")
    parser.add_argument("--type", default="M2", choices=["M1", "M2", "M3", "M4", "M5"])
    parser.add_argument("--width", type=float, default=7.0)
    parser.add_argument("--height", type=float, default=9.0)
    args = parser.parse_args()

    if args.manual:
        run_manual(args.type, args.width, args.height)
    else:
        run_from_archicad(args.type)
