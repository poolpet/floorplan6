"""Diagnostyczny baseline IoU pokoi: generator vs REALNA geometria tropie (refs_geo
vector_traced). Tylko tropie — pozostałe 5 refs_geo mają geometrię zgadniętą (vision).
Najpierw SANITY-CHECK ramki współrzędnych (origin/orientacja), potem IoU per kondygnacja.

Uruchomienie: PYTHONPATH=. venv/bin/python notebooks/tropie_iou_probe.py
"""
import json
from pathlib import Path

from shapely.geometry import Polygon

from core.house_layout import generate_house
from notebooks.reference_benchmark import room_iou, _gen_room_type

GEO = json.loads(Path("notebooks/refs_geo/tropie.json").read_text())
assert GEO.get("geometry_source") == "vector_traced", "IoU tylko dla realnej geometrii"


def _ref_type(rid: str) -> str:
    base = rid.split("_")[0]
    return {"hol": "hol", "podest": "hol", "schody": "schody"}.get(base, base)


def _gen_base_type(rid: str) -> str:
    t = _gen_room_type(rid, is_master=False)
    return "sypialnia" if t == "master_sypialnia" else t


storeys = GEO["storeys"]
parter_geo = next(s for s in storeys if s["storey"] == "parter")
outline = parter_geo["outline"]
poly = Polygon(outline)
bx0, by0, bx1, by1 = poly.bounds
entry = parter_geo.get("entry") or {}
ep = tuple(entry.get("point", [(bx0 + bx1) / 2, by0]))
n_storeys = 2 if any(s["storey"] in ("poddasze", "pietro") for s in storeys) else 1

lay = generate_house(poly, entry_point=ep, num_storeys=n_storeys, time_limit_s=60.0)
print(f"tropie outline bbox = ({bx0:.2f},{by0:.2f})-({bx1:.2f},{by1:.2f})  gen.ok={lay.ok} {lay.message[:50]}")
if not lay.ok:
    raise SystemExit("generator nie zbudował tropie — IoU pominięty")

gbx = lay.boundary.bbox
print(f"frame-check: gen.boundary.bbox={tuple(round(v, 2) for v in gbx)} vs outline=({bx0:.2f},{by0:.2f},{bx1:.2f},{by1:.2f})")
if abs(gbx[0] - bx0) > 0.1 or abs(gbx[1] - by0) > 0.1 or abs(gbx[2] - bx1) > 0.1 or abs(gbx[3] - by1) > 0.1:
    print("⚠️ RAMKA NIESPÓJNA — IoU niżej może być nieufny (origin/skala/y-flip).")


def _iou_for(geo_storey, gen_rooms):
    ref_tp = [(_ref_type(r["id"]), Polygon(r["polygon"])) for r in geo_storey["rooms"]]
    gen_tp = [(_gen_base_type(r.spec.id), r.polygon) for r in gen_rooms]
    return room_iou(gen_tp, ref_tp)


print(f"PARTER room-IoU = {_iou_for(parter_geo, lay.parter_rooms)}")
pod = next((s for s in storeys if s["storey"] in ("poddasze", "pietro")), None)
if pod and lay.pietro_rooms:
    print(f"PODDASZE room-IoU = {_iou_for(pod, lay.pietro_rooms)}")
