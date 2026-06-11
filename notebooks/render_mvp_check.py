"""MVP visual check — rzuty z meblami (do ścian) + drzwiami + oknami.

Regeneruje scenariusze z rzuty/renders_phase4 + jedno mieszkanie, do rzuty/renders_mvp/.
"""
import matplotlib
matplotlib.use("Agg")

from pathlib import Path
from shapely.geometry import Polygon

from core.house_layout import generate_house
from core.furniture import furnish_rooms
from core.models import FloorPlan
from viz.house_preview import render_house_figure
from viz.plan_renderer import render_floor_plan

OUT = Path("rzuty/renders_mvp")
OUT.mkdir(parents=True, exist_ok=True)


def house_2storey():
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])
    lay = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=45.0)
    assert lay.ok, lay.message
    render_house_figure(lay, with_furniture=True,
                        title="Dom 11×8 — MVP (poddasze: strefy niskiej ścianki kolankowej)",
                        save_path=OUT / "1_dwukondygnacyjny.png", show=False)
    print("OK 1_dwukondygnacyjny.png")


def house_single():
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    lay = generate_house(poly, entry_point=(5.0, 0.0), num_storeys=1, time_limit_s=30.0)
    assert lay.ok, lay.message
    fr = furnish_rooms(lay.parter_rooms, boundary=lay.boundary)
    plan = FloorPlan(boundary=lay.boundary, template=None, rooms=lay.parter_rooms)
    render_floor_plan(plan, title="Parterowiec 10×10 — MVP (meble + drzwi + okna)",
                      save_path=OUT / "2_parterowiec.png", show=False, furniture=fr.furniture)
    print("OK 2_parterowiec.png")


def apartment():
    from core.variant_generator import generate_variants
    poly = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
    plan = generate_variants(poly, (5.0, 0.0), "M3", max_variants=1)[0]
    fr = furnish_rooms(plan.rooms, plan.boundary)
    render_floor_plan(plan, title="Mieszkanie M3 — 10×8 — MVP (meble + drzwi + okna)",
                      save_path=OUT / "3_mieszkanie_M3.png", show=False, furniture=fr.furniture)
    print("OK 3_mieszkanie_M3.png")


if __name__ == "__main__":
    house_2storey()
    house_single()
    apartment()
    print("DONE →", OUT)
