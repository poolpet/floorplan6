"""Reality-check (Session 17): GAP vs rozmiar obrysu domu.

Bez zmian w kodzie — odpala istniejacy generate_house + render_two_storey na
kilku obrysach, zeby pokazac ze przerost pokoi (salon ~46 / master ~43) to
artefakt za duzego obrysu, a na realnym ~64 m2/kondygnacje rozmiary sa sensowne.

Zapis PNG -> notebooks/output/.
"""
from pathlib import Path
from shapely.geometry import Polygon

from core.house_layout import generate_house
from viz.house_preview import render_house_figure, house_details_text

OUT = Path(__file__).parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    ("realny_8x8_64m2", 8.0, 8.0),
    ("realny_9x7_63m2", 9.0, 7.0),
    ("zaduzy_10x9_90m2", 10.0, 9.0),
    ("testowy_11x9_99m2", 11.0, 9.0),
]

for name, w, h in CASES:
    poly = Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    layout = generate_house(poly, entry_point=(w / 2, 0.0), num_storeys=2, time_limit_s=30.0)
    print("=" * 60)
    print(f"{name}: obrys {w}x{h} = {w*h:.0f} m2/kondygnacja  ->  ok={layout.ok}")
    if not layout.ok:
        print("  ", layout.message)
        continue
    print(house_details_text(layout))
    png = OUT / f"reality_{name}.png"
    render_house_figure(layout, with_furniture=True,
                        title=f"Dom {w:.0f}x{h:.0f} = {w*h:.0f} m2/kondygn.",
                        save_path=png, show=False)
    print(f"  -> {png}")
