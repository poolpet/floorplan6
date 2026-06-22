"""DIAGNOSTYKA meble→AC: odtwórz OFFLINE (bez ArchiCAD) dwa bugi z rzutu Dawida
(2026-06-08): (1) meble "pływają" / nie są przy ścianach w AC; (2) brak kuchni
w mieszkaniu. Oba są WZGLĘDNE DO POKOJU, więc reprodukują się bez Tapira/AC —
NIE uruchamiamy create_objects, więc NIE ma artefaktu "pustki w origin" (windows=0).

Dla każdego obrysu rysuje DWA panele:
    LEWO  = RENDERER (matplotlib) — geometria solvera `Furniture.polygon`
            (dociśnięta do ściany przez _place_on_wall) → wygląda dobrze.
    PRAWO = ARCHICAD — geometria `extract_furniture()` (stałe wymiary biblioteczne,
            stała oś, BEZ rotacji) → to dostaje AC. Tu meble pływają / wybrzuszają się.

Flagi per mebel:
    AXIS  = oś długa obiektu AC ≠ oś długa boxa solvera (rdzeń H2: brak swapu dim_x/dim_y)
    OUT   = footprint AC wychodzi poza realny polygon pokoju (L/U: kotwica do bbox, nie polygonu)
    DRIFT = przesunięcie centroidu box→AC (m)
Flagi per pokój:
    KUCHNIA = pokój DZIENNA/salon_aneks NIE dostał kitchen_counter (H1).

Uruchom (bez AC):
    PYTHONPATH=. venv/bin/python notebooks/furniture_export_check.py
Zapisuje PNG do rzuty/diag/ i drukuje tabelę flag.
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Polygon, box

from core.models import Room, RoomSpec, Strefa
from core.furniture import furnish_rooms
from core.furniture_extractor import extract_furniture, FURNITURE_LIBRARY_MAP

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "rzuty", "diag")


# ----------------------------------------------------------------------------
# Budowa pokoi (ręczne, deterministyczne — bez CP-SAT)
# ----------------------------------------------------------------------------
def mk_room(rid: str, poly: Polygon, strefa: Strefa, *, okno: bool = False) -> Room:
    spec = RoomSpec(
        id=rid, nazwa=rid, strefa=strefa,
        wymaga_okna=okno, priorytet_fasady=1 if okno else None,
    )
    r = Room(spec=spec, polygon=poly)
    r.update_metrics()
    return r


def l_shape(w: float, h: float, nw: float, nh: float) -> Polygon:
    """Pokój L: prostokąt w×h z wyciętym narożnikiem (prawy-górny) nw×nh."""
    return box(0, 0, w, h).difference(box(w - nw, h - nh, w, h))


# ----------------------------------------------------------------------------
# Analiza: sparuj Furniture (renderer) z FurnitureObject (AC) i policz flagi
# ----------------------------------------------------------------------------
def docked_wall(b, r) -> str:
    bx0, by0, bx1, by1 = b
    rx0, ry0, rx1, ry1 = r
    gaps = {"left": bx0 - rx0, "right": rx1 - bx1, "bottom": by0 - ry0, "top": ry1 - by1}
    return min(gaps, key=gaps.get)


def long_axis(w: float, h: float) -> str:
    if abs(w - h) < 1e-6:
        return "kw"
    return "V" if h > w else "H"


def analyze(rooms: list[Room]):
    """Zwraca (per-piece rows, per-room kitchen flags, paired objs)."""
    fr = furnish_rooms(rooms, boundary=None)  # boundary=None: oś bug niezależny od okien
    objs = extract_furniture(fr, rooms)
    # extract_furniture iteruje fr.furniture w kolejności, pomijając typy bez mapowania
    mapped = [f for f in fr.furniture if f.piece_type in FURNITURE_LIBRARY_MAP]
    assert len(mapped) == len(objs), f"pairing mismatch {len(mapped)} vs {len(objs)}"
    room_poly = {r.spec.id: r.polygon for r in rooms if r.polygon is not None}

    rows = []
    for f, o in zip(mapped, objs):
        rp = room_poly.get(f.room_id)
        b = f.polygon.bounds
        bw, bh = b[2] - b[0], b[3] - b[1]
        box_axis = long_axis(bw, bh)
        obj_axis = long_axis(o.dim_x, o.dim_y)
        axis_mismatch = box_axis != obj_axis and "kw" not in (box_axis, obj_axis)
        obj_rect = box(o.x, o.y, o.x + o.dim_x, o.y + o.dim_y)
        out_poly = rp is not None and not obj_rect.within(rp.buffer(1e-6))
        bc = f.polygon.centroid
        oc = obj_rect.centroid
        drift = math.hypot(bc.x - oc.x, bc.y - oc.y)
        wall = docked_wall(b, rp.bounds) if rp is not None else "—"
        rows.append({
            "room": f.room_id, "piece": f.piece_type, "lib": o.library_part_name,
            "box": f"{bw:.2f}x{bh:.2f}", "obj": f"{o.dim_x:.2f}x{o.dim_y:.2f}",
            "wall": wall, "AXIS": axis_mismatch, "OUT": out_poly, "DRIFT": round(drift, 2),
            "FLOAT": axis_mismatch or out_poly or drift > 0.5,
        })

    # per-pokój: DZIENNA / salon_aneks bez kitchen_counter?
    kitchen_flags = []
    counters = {f.room_id for f in fr.furniture if f.piece_type == "kitchen_counter"}
    for r in rooms:
        key = r.spec.id.split("_")[0]
        is_dayzone = r.spec.strefa == Strefa.DZIENNA or key in ("salon", "kuchnia")
        if is_dayzone and r.spec.id not in counters:
            kitchen_flags.append(r.spec.id)
    return fr, objs, rows, kitchen_flags


# ----------------------------------------------------------------------------
# Render: dwa panele (renderer vs AC)
# ----------------------------------------------------------------------------
def _draw_rooms(ax, rooms):
    for r in rooms:
        if r.polygon is None:
            continue
        xs, ys = r.polygon.exterior.xy
        ax.add_patch(MplPolygon(list(zip(xs, ys)), closed=True,
                                facecolor="#f3f0e9", edgecolor="#555", lw=1.5, zorder=1))
        c = r.polygon.representative_point()
        ax.text(c.x, c.y, r.spec.id, ha="center", va="center",
                fontsize=7, color="#1450a0", zorder=5)


def _draw_furn(ax, polys_labels, color):
    for poly, label, flagged in polys_labels:
        xs, ys = poly.exterior.xy
        ax.add_patch(MplPolygon(list(zip(xs, ys)), closed=True, facecolor="none",
                                edgecolor=("#d11" if flagged else color),
                                lw=(2.2 if flagged else 1.3),
                                hatch=("xx" if flagged else None), zorder=3))


def render_case(name: str, rooms: list[Room], rows, objs, fr, kitchen_flags):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 6.2))
    bounds = [r.polygon.bounds for r in rooms if r.polygon is not None]
    minx = min(b[0] for b in bounds); miny = min(b[1] for b in bounds)
    maxx = max(b[2] for b in bounds); maxy = max(b[3] for b in bounds)
    pad = 0.5

    # LEWO — renderer (Furniture.polygon)
    _draw_rooms(axL, rooms)
    _draw_furn(axL, [(f.polygon, f.piece_type, False) for f in fr.furniture], "#1a8a1a")
    axL.set_title("RENDERER (matplotlib) — to widzisz w podglądzie", fontsize=10)

    # PRAWO — AC (extract_furniture)
    _draw_rooms(axR, rooms)
    flagged_objs = {id(o): r["FLOAT"] for o, r in zip(objs, rows)}
    _draw_furn(axR, [(box(o.x, o.y, o.x + o.dim_x, o.y + o.dim_y),
                      o.piece_type, flagged_objs[id(o)]) for o in objs], "#b8860b")
    axR.set_title("ARCHICAD (extract_furniture) — to dostaje AC", fontsize=10)

    for ax in (axL, axR):
        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
        ax.set_aspect("equal")
        ax.axis("off")

    floats = sum(1 for r in rows if r["FLOAT"])
    sub = f"{name}   |   meble: {len(objs)}   pływają/AXIS/OUT: {floats}"
    if kitchen_flags:
        sub += f"   |   BRAK KUCHNI w: {', '.join(kitchen_flags)}"
    fig.suptitle(sub, fontsize=11, color=("#b00" if (floats or kitchen_flags) else "#070"))
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def print_report(name, rows, kitchen_flags):
    print(f"\n=== {name} ===")
    if kitchen_flags:
        print(f"  ⚠ BRAK KUCHNI (kitchen_counter) w pokojach DZIENNA: {kitchen_flags}")
    if not rows:
        print("  (brak zmapowanych mebli)")
        return
    hdr = f"  {'pokój':14s} {'mebel':14s} {'box(WxH)':11s} {'AC(x×y)':11s} {'ściana':7s} {'AXIS':5s} {'OUT':4s} {'DRIFT':6s}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        print(f"  {r['room']:14s} {r['piece']:14s} {r['box']:11s} {r['obj']:11s} "
              f"{r['wall']:7s} {'YES' if r['AXIS'] else '.':5s} "
              f"{'YES' if r['OUT'] else '.':4s} {r['DRIFT']:<6}")


# ----------------------------------------------------------------------------
# Przypadki testowe (deterministyczne — odwzorowują rzut Dawida + stresy)
# ----------------------------------------------------------------------------
def hand_cases():
    cases = {}

    # A) Mieszkanie: otwarta strefa dzienna salon_aneks (jak "Living room with
    #    kitchenette" u Dawida) + sypialnia + łazienka. Dowodzi H1 (brak kuchni)
    #    + H2 (sofa pływa). salon_aneks key→"salon"→_furnish_living, NIGDY kuchnia.
    cases["A_mieszkanie_salon_aneks"] = [
        mk_room("salon_aneks", box(0, 0, 6, 5.5), Strefa.DZIENNA, okno=True),
        mk_room("sypialnia_1", box(6, 0, 10, 3.5), Strefa.NOCNA, okno=True),
        mk_room("lazienka_1", box(6, 3.5, 8.5, 5.5), Strefa.USLUGOWA),
        mk_room("hub", box(8.5, 3.5, 10, 5.5), Strefa.KOMUNIKACJA),
    ]

    # B) Dom: osobny salon + kuchnia → kitchen_counter ISTNIEJE (kontrola vs A).
    #    Te same meble nadal pływają w AC (extract_furniture wspólny).
    cases["B_dom_salon+kuchnia"] = [
        mk_room("salon_1", box(0, 0, 5, 5), Strefa.DZIENNA, okno=True),
        mk_room("kuchnia_1", box(5, 0, 8, 4), Strefa.DZIENNA, okno=True),
        mk_room("sypialnia_1", box(0, 5, 4, 8.5), Strefa.NOCNA, okno=True),
    ]

    # F) Wąski pokój 3×6 → meble lądują na ścianie W/E (pionowej) → MAKSYMALNY
    #    rozjazd osi: box pionowy 0.9×2.4, AC dostaje 1.6×0.85 poziomo → wybrzusza.
    cases["F_waski_3x6_sciana_WE"] = [
        mk_room("salon_1", box(0, 0, 3, 6), Strefa.DZIENNA, okno=False),
    ]

    # G) Mała kuchnia 2.6×2.6 < kitchen_counter biblioteczny (1.92×2.52) → CLAMP
    #    do rogu min (extract_furniture:124-125).
    cases["G_kuchnia_oversized_clamp"] = [
        mk_room("kuchnia_1", box(0, 0, 2.6, 2.6), Strefa.DZIENNA, okno=False),
    ]

    # D) Sypialnia L-kształtna → _anchor dokuje do bbox (wnęka = pustka) → OUT.
    cases["D_sypialnia_L"] = [
        mk_room("sypialnia_1", l_shape(5, 5, 2.2, 2.2), Strefa.NOCNA, okno=True),
    ]
    return cases


def real_apartment_case():
    """Realny plan M3 (CP-SAT) ~ jak rzut Dawida — best-effort, może flakować."""
    try:
        from core.variant_generator import generate_variants
        poly = box(0, 0, 9.5, 8.0)        # ~76 m², zbliskie M3 z rzutu
        plans = generate_variants(poly, (4.75, 0.0), "M3", max_variants=1)
        if not plans:
            print("\n(real M3: INFEASIBLE dla 9.5×8 — pomijam realny plan)")
            return None
        return plans[0].rooms
    except Exception as e:
        print(f"\n(real M3 pominięty: {e!r})")
        return None


def main():
    print("DIAGNOSTYKA meble→AC (OFFLINE, bez ArchiCAD)")
    print("Bug 1 = meble pływają (AXIS/OUT);  Bug 2 = brak kuchni (KUCHNIA flag)\n")

    all_cases = hand_cases()
    real = real_apartment_case()
    if real is not None:
        all_cases["REAL_M3_apartment"] = real

    for name, rooms in all_cases.items():
        fr, objs, rows, kitchen_flags = analyze(rooms)
        path = render_case(name, rooms, rows, objs, fr, kitchen_flags)
        print_report(name, rows, kitchen_flags)
        print(f"  → {path}")

    print("\nGotowe. Otwórz panele w rzuty/diag/ — porównaj LEWO (renderer) vs PRAWO (AC).")


if __name__ == "__main__":
    main()
