"""Renderuje WZORZEC z geometria (refs_geo/*.json) z powrotem jako rzut PNG.

Model (wg dyrektywy Dawida 2026-06-14):
  - geometria pokoi 1:1 (pozycje/ksztalty wiernie),
  - SCIANY = LINIE bez grubosci, lokalizacja 1:1 (pokoje KAFELKUJA obrys, wspolne
    krawedzie = linie scian); zadnej masy scian,
  - OKNA = informacja KTORE pomieszczenie ma okno i z ktorej strony (swiatlo), bez wymiaru.

Schemat pokoju: {id,label,polygon,area_m2 (netto z tabeli, do wyswietlenia),
  window_sides:[...], on_facade}. Sciany wewnetrzne bloku: internal_walls (linie, ciemne).
Zgodnosc wstecz: jesli sa top-level 'windows' (odcinki) — tez je narysuje.

Uruchomienie:  venv/bin/python notebooks/render_ref_geo.py notebooks/refs_geo/tropie.json
Wynik:         rzuty/refs_geo/<name>_<storey>.png
"""
from __future__ import annotations

import json
import math
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Arc, FancyArrow

ROOM_COLORS = {
    "salon": "#fde7c9", "kuchnia": "#fde7c9", "jadalnia": "#fde7c9",
    "sypialnia": "#dbe9f4", "master_sypialnia": "#c7dbef",
    "lazienka": "#cfeede", "wc": "#cfeede",
    "hol": "#f0f0f0", "podest": "#f0f0f0", "przedpokoj": "#f0f0f0", "wiatrolap": "#f0f0f0",
    "schody": "#e6e0f0",
    "garderoba": "#f0e6e6", "spizarnia": "#f0e6e6", "kotlownia": "#f0e6e6",
    "pralnia": "#f0e6e6", "garaz": "#e3e3e3", "gabinet": "#dbe9f4", "pokoj": "#dbe9f4",
}
DEFAULT_ROOM = "#f6f6f6"
EXT_WALL = "#222222"      # sciana zewnetrzna / obrys (linia)
INT_WALL = "#555555"      # sciana wewnetrzna (linia)
PARTY_WALL = "#111111"    # sciana wspolna w bloku (bez swiatla) — gruba ciemna


def _poly_centroid(pts):
    n = len(pts)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr; cx += (x0 + x1) * cr; cy += (y0 + y1) * cr
    if abs(a) < 1e-9:
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return sum(xs) / n, sum(ys) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def _bbox(outline):
    xs = [p[0] for p in outline]; ys = [p[1] for p in outline]
    return min(xs), min(ys), max(xs), max(ys)


def _draw_stairs(ax, st):
    fp = st["footprint"]
    xs = [p[0] for p in fp]; ys = [p[1] for p in fp]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    n_str = 8
    top0 = y0 + 0.45 * h
    for i in range(n_str + 1):
        yy = top0 + (y1 - top0) * i / n_str
        ax.plot([x0 + 0.06, x1 - 0.06], [yy, yy], color="#666", lw=0.7, zorder=5)
    pivot = (x1 - 0.06, top0)
    for k in range(5):
        ang = math.radians(180 + 18 * k)
        rr = min(w, top0 - y0) * 0.95
        ax.plot([pivot[0], pivot[0] + rr * math.cos(ang)],
                [pivot[1], pivot[1] + rr * math.sin(ang)], color="#666", lw=0.7, zorder=5)
    ax.add_patch(FancyArrow(x0 + 0.5 * w, y0 + 0.15 * h, 0, 0.55 * h, width=0.015,
                            head_width=0.18, head_length=0.18, length_includes_head=True,
                            color="#b03030", zorder=6))
    ax.text((x0 + x1) / 2, y1 - 0.10 * h, f"schody\n({st.get('kind','?')})",
            ha="center", va="top", fontsize=6.5, color="#b03030", zorder=7)


def _draw_door(ax, d):
    x, y = d["point"]; r = 0.7
    wall = d.get("wall", "v"); swing = d.get("swing", 1); typ = d.get("type", "door")
    if typ == "opening":
        if wall == "v":
            ax.plot([x, x], [y - 0.45, y + 0.45], color="#ffffff", lw=4, zorder=4)
        else:
            ax.plot([x - 0.45, x + 0.45], [y, y], color="#ffffff", lw=4, zorder=4)
        return
    if wall == "v":
        ax.plot([x, x + swing * r], [y, y], color="#7a5c3a", lw=1.2, zorder=6)
        ax.add_patch(Arc((x, y), 2 * r, 2 * r, theta1=(0 if swing > 0 else 90),
                         theta2=(90 if swing > 0 else 180), color="#7a5c3a", lw=0.8, zorder=6))
    else:
        ax.plot([x, x], [y, y + swing * r], color="#7a5c3a", lw=1.2, zorder=6)
        ax.add_patch(Arc((x, y), 2 * r, 2 * r, theta1=(0 if swing > 0 else 180),
                         theta2=(90 if swing > 0 else 270), color="#7a5c3a", lw=0.8, zorder=6))


def _room_edge_on_side(poly, side, bb, tol=0.12):
    """Zwraca (a,b) zakres krawedzi pokoju lezacej na danej stronie obrysu (albo None)."""
    x0, y0, x1, y1 = bb
    if side in ("west", "east"):
        target = x0 if side == "west" else x1
        ys = [p[1] for p in poly if abs(p[0] - target) < tol]
        if len(ys) >= 2:
            return min(ys), max(ys), target, "v"
    else:
        target = y0 if side == "south" else y1
        xs = [p[0] for p in poly if abs(p[1] - target) < tol]
        if len(xs) >= 2:
            return min(xs), max(xs), target, "h"
    return None


def _draw_window_for_room(ax, room, bb):
    for side in room.get("window_sides", []) or []:
        e = _room_edge_on_side(room["polygon"], side, bb)
        if not e:
            continue
        lo, hi, t, orient = e
        m = 0.18 * (hi - lo)
        a, b = lo + m, hi - m
        if orient == "v":
            ax.plot([t, t], [a, b], color="#2f6fb0", lw=4.5, solid_capstyle="butt", zorder=7)
            ax.plot([t, t], [a, b], color="#bfe3ff", lw=1.6, zorder=8)
        else:
            ax.plot([a, b], [t, t], color="#2f6fb0", lw=4.5, solid_capstyle="butt", zorder=7)
            ax.plot([a, b], [t, t], color="#bfe3ff", lw=1.6, zorder=8)


def _draw_window_seg(ax, seg):  # zgodnosc wstecz (stary model odcinkow)
    (x0, y0), (x1, y1) = seg
    ax.plot([x0, x1], [y0, y1], color="#2f6fb0", lw=4.5, solid_capstyle="butt", zorder=7)
    ax.plot([x0, x1], [y0, y1], color="#bfe3ff", lw=1.6, zorder=8)


def render_storey(ax, st, name):
    outline = st["outline"]
    bb = _bbox(outline)
    # pokoje — kafelkuja obrys; wypelnienie + linie scian (krawedzie)
    for r in st["rooms"]:
        base = r["id"] if r["id"] in ROOM_COLORS else r["id"].split("_")[0]
        color = ROOM_COLORS.get(r["id"], ROOM_COLORS.get(base, DEFAULT_ROOM))
        ax.add_patch(MplPolygon(r["polygon"], closed=True, facecolor=color,
                                edgecolor=INT_WALL, lw=1.1, zorder=2))
    # obrys (sciany zewnetrzne) jako linia na wierzchu
    ax.add_patch(MplPolygon(outline, closed=True, fill=False, edgecolor=EXT_WALL,
                            lw=2.2, zorder=3))
    # sciany wewnetrzne bloku (bez swiatla) — gruba ciemna linia
    for seg in st.get("internal_walls", []) or []:
        s = seg["seg"] if isinstance(seg, dict) else seg
        (x0, y0), (x1, y1) = s
        ax.plot([x0, x1], [y0, y1], color=PARTY_WALL, lw=5, solid_capstyle="butt", zorder=6)
    # okna — per pokoj (informacja: ktore pomieszczenie ma swiatlo i z ktorej strony)
    for r in st["rooms"]:
        _draw_window_for_room(ax, r, bb)
    for w in st.get("windows", []) or []:  # stary model (zgodnosc wstecz)
        _draw_window_seg(ax, w["seg"])
    # etykiety pokoi (label + m2 z tabeli)
    for r in st["rooms"]:
        cx, cy = _poly_centroid(r["polygon"])
        lab = "\n".join(textwrap.wrap(r["label"], 18))
        area = r.get("area_m2")
        txt = lab + (f"\n{area:.1f} m²" if area else "")
        ax.text(cx, cy, txt, ha="center", va="center", fontsize=7, zorder=9)
    if st.get("stairs"):
        _draw_stairs(ax, st["stairs"])
    for d in st.get("doors", []) or []:
        _draw_door(ax, d)
    if st.get("entry"):
        e = dict(st["entry"]); e["type"] = "entry"; e.setdefault("swing", 1)
        _draw_door(ax, e)
        ex, ey = st["entry"]["point"]
        ax.text(ex + 0.15, ey - 0.5, "WEJSCIE", fontsize=6.5, color="#1a6", zorder=9)

    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], color="#2f6fb0", lw=4, label="okno (pomieszczenie ze światłem)"),
           Line2D([0], [0], color="#7a5c3a", lw=1.3, label="drzwi"),
           Line2D([0], [0], color="#b03030", lw=1.5, label="schody"),
           Line2D([0], [0], color=EXT_WALL, lw=2.2, label="ściana (linia)")]
    if st.get("internal_walls"):
        leg.append(Line2D([0], [0], color=PARTY_WALL, lw=4, label="ściana wewn. bloku (bez światła)"))
    ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, -0.13),
              ncol=3, fontsize=6.5, frameon=False)

    x0, y0, x1, y1 = bb
    pad = 0.6
    ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal"); ax.axis("off")
    extra = " | strefa dzienna open-plan" if st.get("open_plan_day_zone") else ""
    knee = " | obrys dachu (knee-wall)" if st.get("roof_knee_wall") else ""
    ax.set_title(f"{name} — {st['storey']}  ({x1-x0:.2f}×{y1-y0:.2f} m){extra}{knee}", fontsize=10)


def main(path):
    data = json.loads(Path(path).read_text())
    name = data["name"]
    out_dir = Path("rzuty/refs_geo"); out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for st in data["storeys"]:
        fig, ax = plt.subplots(figsize=(7.5, 5.2))
        render_storey(ax, st, name)
        fig.tight_layout()
        out = out_dir / f"{name}_{st['storey']}.png"
        fig.savefig(out, dpi=150, bbox_inches="tight"); plt.close(fig)
        written.append(str(out))
    print("ZAPISANO:")
    for w in written:
        print(" ", w)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notebooks/refs_geo/tropie.json")
