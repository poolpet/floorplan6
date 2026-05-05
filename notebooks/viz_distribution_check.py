"""
Sesja 2 — Walidacja wizualna: czy salon naturalnie absorbuje nadmiar po Fazie A?

Generuje 3 warianty M3 dla obrysu 12×10 (= 120 m², dużo nadmiaru).
Wypisuje powierzchnie pokoi i renderuje PNG do `notebooks/output/`.

Po Fazie A: łazienka ≤5 m² i WC ≤3 m². Pytanie: czy salon dostaje >> minimum,
czy nadmiar idzie gdzie indziej (np. sypialnie nadęte, hub > 15%).
"""
from pathlib import Path
from shapely.geometry import Polygon

from core.variant_generator import generate_variants
from viz.plan_renderer import render_floor_plan

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

# 12×10 = 120 m². Min dla M3: ~50-60 m² (salon 16, sypialnia 9, sypialnia 6, lazienka 4.5, hub 6)
# → nadmiar ~60 m² do rozdzielenia. Doskonały przypadek pod testowanie.
W, H = 12.0, 10.0
poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
entry = (W / 2, 0.0)

print(f"=== Boundary: {W}×{H} = {W*H:.1f} m² ===\n")
plans = generate_variants(poly, entry, "M3", max_variants=3)
print(f"Wygenerowano {len(plans)} wariantów\n")

for i, plan in enumerate(plans):
    print(f"--- Wariant {i+1} (template: {plan.template.id}, score: {plan.score:.2f}) ---")
    total = sum(r.area for r in plan.rooms)
    print(f"  Suma pokoi: {total:.2f} m² (boundary: {plan.boundary.area:.2f} m²)")
    for r in sorted(plan.rooms, key=lambda x: -x.area):
        pct = 100 * r.area / plan.boundary.area
        print(f"  {r.spec.id:20s} {r.area:6.2f} m² ({pct:5.1f}%)  "
              f"min={r.spec.min_powierzchnia:.1f}, opt={r.spec.opt_powierzchnia:.1f}")
    out = OUT_DIR / f"M3_12x10_v{i+1}.png"
    render_floor_plan(plan, save_path=out, show=False)
    print(f"  → {out}")
    print()

print("=== KONIEC ===")
