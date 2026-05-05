"""
Test E2E z ArchiCAD: odczyt obrysu → generowanie rzutu → render PNG.

UŻYCIE:
  1. W AC: narysuj 4 ściany tworzące obrys mieszkania (np. 8×6m)
  2. Zaznacz wszystkie 4 ściany (drag-select lub Ctrl+A)
  3. PYTHONPATH=. python notebooks/test_archicad_e2e.py [M2|M3|M4]

EKSPORT do AC: tylko po akceptacji Dawida — osobny skrypt `test_archicad_export.py`.
"""
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)


def main(mtype: str = "M3"):
    from bridge.tapir_connection import TapirConnection
    from bridge.boundary_reader import read_boundary_from_archicad
    from core.boundary_analyzer import analyze_boundary
    from core.variant_generator import generate_variants
    from viz.plan_renderer import render_floor_plan

    print("=== Test E2E: ArchiCAD → FloorPlan6 ===\n")

    print("[1/4] Łączenie z ArchiCAD...")
    tapir = TapirConnection()
    tapir.connect()
    print("    ✓ Połączono (port 19723)\n")

    print("[2/4] Odczyt zaznaczonego obrysu...")
    selected = tapir.get_selected_elements()
    if not selected:
        print("    ✗ Brak zaznaczonych elementów w ArchiCAD!")
        print("    → Zaznacz 4 ściany tworzące obrys mieszkania i uruchom ponownie.")
        sys.exit(1)
    print(f"    Zaznaczonych elementów: {len(selected)}")

    polygon, entry_point, wall_types = read_boundary_from_archicad(tapir)
    print(f"    ✓ Obrys: {polygon.area:.2f} m² (bbox: {polygon.bounds})")
    print(f"    ✓ Entry point: ({entry_point[0]:.2f}, {entry_point[1]:.2f})")
    if wall_types:
        print(f"    ✓ Typy ścian: {len(wall_types)} krawędzi")
    print()

    print(f"[3/4] Generowanie wariantów {mtype}...")
    boundary = analyze_boundary(polygon, entry_point, wall_types)
    print(f"    Fasady: {len(boundary.facade_edges)}, Internal: {len(boundary.internal_edges)}")

    variants = generate_variants(
        polygon=polygon,
        entry_point=entry_point,
        mtype=mtype,
        max_variants=3,
    )
    if not variants:
        print("    ✗ Brak wariantów (solver INFEASIBLE dla tego obrysu)")
        sys.exit(1)
    print(f"    ✓ {len(variants)} wariantów\n")

    for i, plan in enumerate(variants):
        status = "OK" if plan.is_valid else f"BŁĘDY:{len(plan.validation_errors)}"
        print(f"    Wariant {i+1}: score={plan.score:.3f} [{status}] (template={plan.template.id})")
        for room in sorted(plan.rooms, key=lambda r: -r.area):
            pct = 100 * room.area / plan.boundary.area
            print(f"      {room.spec.nazwa:30s} {room.area:5.1f}m² ({pct:4.1f}%)")
        print()

    print("[4/4] Render PNG...")
    best = variants[0]
    out = OUT_DIR / f"archicad_e2e_{mtype}.png"
    render_floor_plan(best, save_path=out, show=False,
                      title=f"AC E2E {mtype} — score: {best.score:.3f}")
    print(f"    ✓ {out}\n")

    print("=== KONIEC ===")
    print(f"Najlepszy wariant zapisany do: {out}")
    print("Aby wyeksportować strefy do AC: uruchom test_archicad_export.py")


if __name__ == "__main__":
    mtype = sys.argv[1] if len(sys.argv) > 1 else "M3"
    if mtype not in ("M1", "M2", "M3", "M4", "M5"):
        print(f"Nieprawidłowy typ: {mtype}. Użyj M1/M2/M3/M4/M5")
        sys.exit(1)
    main(mtype)
