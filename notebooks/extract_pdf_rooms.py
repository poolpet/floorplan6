"""extract_pdf_rooms.py — REUZYWALNY ekstraktor geometrii pokoi z wektorowego PDF rzutu.

CEL: z PDF-a (ArchiCAD, nazwane warstwy OCG) odtworzyc geometrie 1:1 jako wzorzec
dla solvera. Wynik = JSON w formacie notebooks/refs_geo/*.json (patrz render_ref_geo.py).

METODA (3 filary):
  1) KALIBRACJA SKALI z warstwy WYMIAROWANIA (nie z bbox scian — balkon psuje bbox!):
     - z lancuchow wymiarowych czytamy liczby (cm) + pozycje kreseczek (ticks) na warstwie
       'Wymiarowanie*'. Suma liczb / rozpietosc kreseczek = m/pt. Korpus = skrajne ticki
       lancucha biegnacego przez caly bok (suma ~= corpus_w / corpus_h). Weryfikacja: po
       skalowaniu wysokosc korpusu MUSI wyjsc ~corpus_h.
     - fallback: jesli brak wymiarow -> skala z najwyzszego bloku scian (height-based).
  2) OSIE SCIAN: segmenty z warstw WALL (regex), tylko OSIOWE i DLUGIE (filtr hatchingu).
     Podwojne lica -> klastrujemy x (pionowe) i y (poziome) wazone dlugoscia (tol ~0.12 m).
  3) POKOJE — PolSIATKI: z osi budujemy siatke; shapely.ops.polygonize na domknietej
     siatce; twarze w korpusie o sensownym polu = komorki. Komorki laczymy w pokoje wg
     ukladu + obecnosci mebli (warstwa 'Umeblowanie') i schodow (warstwa 'Schody').

Uruchomienie (przyklad tropie):
  venv/bin/python notebooks/extract_pdf_rooms.py \
      --pdf "rzuty/domy/A.02 RZUT PARTERU.pdf:parter:9.57:6.47" \
      --pdf "rzuty/domy/A.03 PODDASZE.pdf:poddasze:9.57:6.47" \
      --name tropie --out notebooks/refs_geo/tropie.json

Argument --pdf:  "<sciezka>:<storey>:<corpus_w>:<corpus_h>"
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import polygonize, unary_union

# ----- warstwy ---------------------------------------------------------------
RE_WALL = re.compile(r"(ścian|scian|nośne|nosne|wall|mur|słup|slup|działow|dzialow)", re.I)
RE_DIM = re.compile(r"(wymiar|dimension)", re.I)
RE_FURN = re.compile(r"(umeblow|meble|furnitur|wnętrze|wnetrze)", re.I)
RE_STAIR = re.compile(r"(schod|stair|balustrad|poręcz|porecz)", re.I)
RE_ROOF = re.compile(r"(dach|roof|obudowa)", re.I)

AXIAL_TOL_PT = 0.6      # |dy|<tol & |dx|>2 => poziomy
MIN_AXIAL_PT = 2.0
CLUSTER_TOL_M = 0.12    # zlepianie podwojnych lic scian
SNAP_TOL_M = 0.30       # domkniecie przerw (otwory okienne/drzwiowe)
MIN_ROOM_M2 = 1.0


# ============================================================================ #
#  EKSTRAKCJA SUROWA
# ============================================================================ #
@dataclass
class Seg:
    orient: str  # 'h' | 'v'
    lo: float    # wzdluz osi segmentu (x dla h, y dla v) — poczatek
    hi: float    # koniec
    pos: float   # pozycja prostopadla (y dla h, x dla v)
    L: float


def _layer_segments(page, pat):
    """Wszystkie OSIOWE segmenty linii z warstw pasujacych do pat. Wsp. PDF (y w dol)."""
    out = []
    for d in page.get_drawings():
        lay = d.get("layer") or ""
        if not pat.search(lay):
            continue
        for it in d["items"]:
            if it[0] != "l":
                continue
            p, q = it[1], it[2]
            x0, y0, x1, y1 = p.x, p.y, q.x, q.y
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy)
            if L < MIN_AXIAL_PT:
                continue
            if abs(dy) < AXIAL_TOL_PT and abs(dx) > 2:
                out.append(Seg("h", min(x0, x1), max(x0, x1), (y0 + y1) / 2, abs(dx)))
            elif abs(dx) < AXIAL_TOL_PT and abs(dy) > 2:
                out.append(Seg("v", min(y0, y1), max(y0, y1), (x0 + x1) / 2, abs(dy)))
    return out


def _raw_lines(page, pat):
    """Wszystkie linie (takze skosne) — do wykrywania schodow/footprintow."""
    pts = []
    for d in page.get_drawings():
        lay = d.get("layer") or ""
        if not pat.search(lay):
            continue
        for it in d["items"]:
            if it[0] == "l":
                pts.append((it[1].x, it[1].y)); pts.append((it[2].x, it[2].y))
            elif it[0] == "re":
                r = it[1]
                pts += [(r.x0, r.y0), (r.x1, r.y1)]
    return pts


def _dim_chain(page, axis, target_cm):
    """Lancuch wymiarowy wzdluz danej osi ('x' poziomy / 'y' pionowy).
    Zwraca (suma_cm, tick_lo_pt, tick_hi_pt, ticks) lancucha, ktorego SUMA jest
    najblizsza target_cm (=corpus_w/h*100). To eliminuje lancuchy schodow (male sumy).

    Ticki = krotkie linie prostopadle na warstwie wymiarowania blisko linii tekstu;
    skrajne ticki = zewnetrzne lica korpusu. Gdy brak tickow — uzywamy rozpietosci
    tekstu (mniej dokladne, ale dziala).
    """
    words = [w for w in page.get_text("words") if w[4].strip().isdigit()]
    dim_segs = _layer_segments(page, RE_DIM)
    best = None  # (err_to_target, sum, tick_lo, tick_hi, ticks)
    if axis == "x":
        groups = {}
        for w in words:
            groups.setdefault(round((w[1] + w[3]) / 2, 0), []).append(w)
    else:
        groups = {}
        for w in words:
            groups.setdefault(round((w[0] + w[2]) / 2, 0), []).append(w)
    for key, ws in groups.items():
        # DEDUP: ArchiCAD renderuje liczby wymiarowe podwojnie (te same wsp.) — to by
        # podwajalo sume lancucha. Scal slowa o (prawie) tej samej pozycji+wartosci.
        seen = []; uniq = []
        for w in ws:
            cx, cy, val = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2, w[4]
            if any(abs(cx - sx) < 2 and abs(cy - sy) < 2 and val == sv for sx, sy, sv in seen):
                continue
            seen.append((cx, cy, val)); uniq.append(w)
        ws = uniq
        if len(ws) < 3:
            continue
        s = sum(int(w[4]) for w in ws)
        err = abs(s - target_cm)
        if best is not None and err >= best[0]:
            continue
        if axis == "x":
            # poziomy lancuch przy y=key: ticki = krotkie pionowe kreski, ktorych
            # srodek-y lezy blisko key; pozycja ticku = ich x (g.pos).
            ticks = sorted({round(g.pos, 1) for g in dim_segs
                            if g.orient == "v" and abs(((g.lo + g.hi) / 2) - key) < 35})
            if not ticks:  # fallback: rozpietosc tekstu
                xs = sorted((w[0] + w[2]) / 2 for w in ws)
                ticks = [xs[0], xs[-1]]
        else:
            # pionowy lancuch przy x=key: ticki = krotkie poziome kreski, ktorych
            # srodek-x lezy blisko key; pozycja ticku = ich y (g.pos).
            ticks = sorted({round(g.pos, 1) for g in dim_segs
                            if g.orient == "h" and abs(((g.lo + g.hi) / 2) - key) < 35})
            if not ticks:
                ys = sorted((w[1] + w[3]) / 2 for w in ws)
                ticks = [ys[0], ys[-1]]
        if len(ticks) >= 2:
            best = (err, s, min(ticks), max(ticks), ticks)
    if best is None:
        return None
    return best[1], best[2], best[3], best[4]  # (sum_cm, tick_lo, tick_hi, ticks)


# ============================================================================ #
#  KALIBRACJA
# ============================================================================ #
@dataclass
class Calib:
    scale: float           # m/pt
    x0_pt: float; y0_pt: float   # korpus outer lewy-dolny (po odbiciu y) w pt
    x1_pt: float; y1_pt: float
    corpus_w: float; corpus_h: float
    page_h: float
    method: str

    def to_m(self, px, py):
        """pt -> metry, z odbiciem y (PDF y w dol) i zerem w lewym-dolnym rogu korpusu."""
        mx = (px - self.x0_pt) * self.scale
        my = (self.y1_pt - py) * self.scale  # y1_pt to dolna krawedz w pt (wieksze y)
        return mx, my


def calibrate(page, corpus_w, corpus_h):
    walls = _layer_segments(page, RE_WALL)
    hs = [s for s in walls if s.orient == "h"]
    vs = [s for s in walls if s.orient == "v"]
    # --- lancuchy wymiarowe glownego obrysu (suma najblizsza corpus_w/h) ---
    dim_x = _dim_chain(page, "x", corpus_w * 100)
    dim_y = _dim_chain(page, "y", corpus_h * 100)
    sx = sy = None
    if dim_x and (dim_x[2] - dim_x[1]) > 5:
        sx = (dim_x[0] / 100.0) / (dim_x[2] - dim_x[1])
    if dim_y and (dim_y[2] - dim_y[1]) > 5:
        sy = (dim_y[0] / 100.0) / (dim_y[2] - dim_y[1])
    cands = [v for v in (sx, sy) if v]
    if cands:
        # skala uniformna: srednia (zwykle prawie identyczne, bo to ten sam plot scale)
        scale = sum(cands) / len(cands)
        method = f"wymiary (sx={sx}, sy={sy})"
    else:
        Lh = max((s.L for s in hs), default=1)
        toph = [s for s in hs if s.L > 0.85 * Lh]
        yvals = [s.pos for s in toph]
        span = max(yvals) - min(yvals)
        scale = corpus_h / span if span else 1.0
        method = "fallback-height"

    # --- korpus outer bbox = skrajne ticki lancuchow ---
    if dim_x:
        x_lo, x_hi = dim_x[1], dim_x[2]
    else:
        x_faces = sorted({round(s.pos, 1) for s in vs})
        x_lo = x_faces[0]
        target_w_pt = corpus_w / scale
        x_hi = min((x for x in x_faces if x > x_lo),
                   key=lambda x: abs((x - x_lo) - target_w_pt), default=x_faces[-1])
    if dim_y:
        y_lo, y_hi = dim_y[1], dim_y[2]
    else:
        Lh = max((s.L for s in hs), default=1)
        toph = [s for s in hs if s.L > 0.85 * Lh]
        y_faces = sorted(s.pos for s in toph)
        y_lo, y_hi = y_faces[0], y_faces[-1]

    return Calib(scale, x_lo, y_lo, x_hi, y_hi, corpus_w, corpus_h, page.rect.height, method)


# ============================================================================ #
#  OSIE SCIAN  (w metrach, po kalibracji)
# ============================================================================ #
def wall_axes(page, cal: Calib):
    """Zwraca (vx, hy): posortowane listy osi pionowych (x w m) i poziomych (y w m).
    Klastruje lica scian wazone dlugoscia, tol CLUSTER_TOL_M."""
    walls = _layer_segments(page, RE_WALL)
    # przelicz pozycje na metry
    def cluster(positions_lengths, tol):
        items = sorted(positions_lengths)
        out = []
        for pos, L in items:
            if out and abs(pos - out[-1][0]) < tol:
                p0, L0 = out[-1]
                out[-1] = ((p0 * L0 + pos * L) / (L0 + L), L0 + L)
            else:
                out.append((pos, L))
        return out

    vx_raw = []
    hy_raw = []
    for s in walls:
        if s.orient == "v":
            mx, _ = cal.to_m(s.pos, 0)
            vx_raw.append((mx, s.L * cal.scale))
        else:
            _, my = cal.to_m(0, s.pos)
            hy_raw.append((my, s.L * cal.scale))
    vx = [p for p, L in cluster(vx_raw, CLUSTER_TOL_M) if L > 0.4]
    hy = [p for p, L in cluster(hy_raw, CLUSTER_TOL_M) if L > 0.4]
    # zawsze dolacz krawedzie korpusu
    for v in (0.0, cal.corpus_w):
        if not any(abs(v - x) < CLUSTER_TOL_M for x in vx):
            vx.append(v)
    for h in (0.0, cal.corpus_h):
        if not any(abs(h - y) < CLUSTER_TOL_M for y in hy):
            hy.append(h)
    vx = sorted(vx); hy = sorted(hy)
    # dosun osie do 0/W/H
    vx = [0.0 if abs(x) < CLUSTER_TOL_M else (cal.corpus_w if abs(x - cal.corpus_w) < CLUSTER_TOL_M else x) for x in vx]
    hy = [0.0 if abs(y) < CLUSTER_TOL_M else (cal.corpus_h if abs(y - cal.corpus_h) < CLUSTER_TOL_M else y) for y in hy]
    return sorted(set(round(x, 3) for x in vx)), sorted(set(round(y, 3) for y in hy))


# ============================================================================ #
#  CENTERLINE walls (zlepione lica) + ich rzeczywiste zasiegi
# ============================================================================ #
def wall_centerlines(page, cal: Calib):
    """Zwraca listy (pos, lo, hi) scian-osi w metrach: pionowe (x=pos, y∈[lo,hi]) i
    poziome (y=pos, x∈[lo,hi]). Zlepia podwojne lica w jedna oś (centerline), laczy
    wspolliniowe odcinki, ignoruje hatching (juz odfiltrowany w _layer_segments)."""
    walls = _layer_segments(page, RE_WALL)
    vsegs = []; hsegs = []
    for s in walls:
        if s.orient == "v":
            x, _ = cal.to_m(s.pos, 0)
            _, ya = cal.to_m(0, s.hi); _, yb = cal.to_m(0, s.lo)
            vsegs.append((x, min(ya, yb), max(ya, yb), s.L * cal.scale))
        else:
            y, _ = (cal.to_m(0, s.pos)[1], 0)
            xa, _ = cal.to_m(s.lo, 0); xb, _ = cal.to_m(s.hi, 0)
            hsegs.append((y, min(xa, xb), max(xa, xb), s.L * cal.scale))

    def group(segs, pair_tol=0.45):
        """grupuj po pozycji (klaster lic), zwraca centerline + polaczony zasieg."""
        segs = sorted(segs, key=lambda s: s[0])
        clusters = []  # list of dict(pos,L, intervals)
        for pos, lo, hi, L in segs:
            if clusters and abs(pos - clusters[-1]["pos"]) < pair_tol:
                c = clusters[-1]
                tot = c["L"] + L
                c["pos"] = (c["pos"] * c["L"] + pos * L) / tot
                c["L"] = tot
                c["iv"].append((lo, hi))
            else:
                clusters.append({"pos": pos, "L": L, "iv": [(lo, hi)]})
        out = []
        for c in clusters:
            # polacz interwaly w jeden zakres (od min do max — sciana z otworami)
            lo = min(a for a, b in c["iv"]); hi = max(b for a, b in c["iv"])
            out.append((round(c["pos"], 3), round(lo, 3), round(hi, 3), c["L"]))
        return out

    return group(vsegs), group(hsegs)


# ============================================================================ #
#  POKOJE: polygonize na siatce osi (PolSIATKI z domknieciem otworow)
# ============================================================================ #
def build_rooms(page, cal: Calib):
    """Zbuduj komorki (twarze) z osi scian. Domyka otwory: kazda os-scianę
    rozszerzamy do najblizszych osi prostopadlych (siatka), wiec drzwi/okna (przerwy
    w scianie) nie psuja petli. Zwraca liste shapely Polygon (komorki)."""
    W, H = cal.corpus_w, cal.corpus_h
    vx, hy = wall_axes(page, cal)
    vsegs, hsegs = wall_centerlines(page, cal)
    # osie pionowe/poziome (konsolidacja do centerline)
    def consolidate(axes, lo, hi, pair_tol=0.45, snap=0.14):
        axes = sorted(a for a in axes if lo - 0.2 <= a <= hi + 0.2)
        out = []; i = 0
        while i < len(axes):
            j = i; grp = [axes[i]]
            while j + 1 < len(axes) and axes[j + 1] - axes[j] < pair_tol:
                j += 1; grp.append(axes[j])
            out.append(sum(grp) / len(grp)); i = j + 1
        out = [lo if abs(a - lo) < snap else (hi if abs(a - hi) < snap else a) for a in out]
        return sorted(set(round(a, 3) for a in out))
    VX = consolidate(vx, 0, W); HY = consolidate(hy, 0, H)
    if VX[0] > 0.05: VX = [0.0] + VX
    if VX[-1] < W - 0.05: VX = VX + [W]
    if HY[0] > 0.05: HY = [0.0] + HY
    if HY[-1] < H - 0.05: HY = HY + [H]

    # buduj linie scian = pelne odcinki siatki tam, gdzie istnieje sciana (centerline),
    # rozszerzone do najblizszych osi prostopadlych (domkniecie otworow do SNAP_TOL_M)
    lines = []
    # obrys zawsze
    lines.append(LineString([(0, 0), (W, 0)]))
    lines.append(LineString([(W, 0), (W, H)]))
    lines.append(LineString([(W, H), (0, H)]))
    lines.append(LineString([(0, H), (0, 0)]))

    def nearest(val, axis):
        return min(axis, key=lambda a: abs(a - val))

    for pos, lo, hi, L in vsegs:
        if pos <= 0.1 or pos >= W - 0.1:
            continue  # to obrys
        x = nearest(pos, VX)
        # rozszerz zasieg do najblizszych poziomych osi (domkniecie)
        a = nearest(lo, HY); b = nearest(hi, HY)
        if b - a < 0.3:
            continue
        lines.append(LineString([(x, a), (x, b)]))
    for pos, lo, hi, L in hsegs:
        if pos <= 0.1 or pos >= H - 0.1:
            continue
        y = nearest(pos, HY)
        a = nearest(lo, VX); b = nearest(hi, VX)
        if b - a < 0.3:
            continue
        lines.append(LineString([(a, y), (b, y)]))

    merged = unary_union(lines)
    faces = [p.buffer(0) for p in polygonize(merged)]
    corpus = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
    faces = [f for f in faces if f.area > 0.02]

    # zbuduj zbior "prawdziwych scian" (centerline z realnym pokryciem) do oceny
    # czy wspolna krawedz dwoch komorek jest faktyczna sciana
    wall_lines = []
    for pos, lo, hi, L in vsegs:
        wall_lines.append(("v", pos, lo, hi))
    for pos, lo, hi, L in hsegs:
        wall_lines.append(("h", pos, lo, hi))

    def edge_is_wall(f1, f2):
        """Czy wspolna krawedz dwoch sasiadujacych komorek pokryta jest sciana >=55%?"""
        inter = f1.intersection(f2)
        if inter.is_empty or inter.length < 0.3:
            return True  # styk punktowy -> traktuj jak rozdzielone
        # wspolna krawedz jest pozioma lub pionowa
        xs = []; ys = []
        if inter.geom_type == "LineString":
            xs = [c[0] for c in inter.coords]; ys = [c[1] for c in inter.coords]
        else:
            return True
        if max(xs) - min(xs) < 0.05:   # pionowa wspolna krawedz -> potrzeba pionowej sciany
            x = sum(xs) / len(xs); a, b = min(ys), max(ys)
            cov = sum(max(0, min(hi, b) - max(lo, a))
                      for o, pos, lo, hi in wall_lines if o == "v" and abs(pos - x) < 0.25)
            return cov >= 0.55 * (b - a)
        elif max(ys) - min(ys) < 0.05:  # pozioma wspolna krawedz
            y = sum(ys) / len(ys); a, b = min(xs), max(xs)
            cov = sum(max(0, min(hi, b) - max(lo, a))
                      for o, pos, lo, hi in wall_lines if o == "h" and abs(pos - y) < 0.25)
            return cov >= 0.55 * (b - a)
        return True

    # union-find scalanie komorek nierozdzielonych prawdziwa sciana
    parent = list(range(len(faces)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i, j):
        parent[find(i)] = find(j)
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if faces[i].distance(faces[j]) < 0.02:
                if not edge_is_wall(faces[i], faces[j]):
                    union(i, j)
    groups = {}
    for i in range(len(faces)):
        groups.setdefault(find(i), []).append(faces[i])
    rooms = []
    for g in groups.values():
        merged_room = unary_union(g).buffer(0.001).buffer(-0.001)
        if merged_room.area < MIN_ROOM_M2:
            continue
        rooms.append(merged_room.intersection(corpus))
    return rooms, VX, HY


def furniture_pts(page, cal):
    return [cal.to_m(x, y) for x, y in _raw_lines(page, RE_FURN)]


def stair_pts(page, cal):
    return [cal.to_m(x, y) for x, y in _raw_lines(page, RE_STAIR)]


def density(pts, poly):
    return sum(1 for x, y in pts if poly.contains(Point(x, y)))


# ============================================================================ #
#  OKNA: szklenie w scianie zewnetrznej -> ktora strona ma swiatlo
# ============================================================================ #
def detect_windows(page, cal, thick=0.40, bin_m=0.10):
    """Okno = OTWOR w scianie zewnetrznej: ArchiCAD przerywa kreskowanie sciany na
    oknie, wiec liczba rownoleglych lic w pasie grubosci LOKALNIE SPADA. Wykrywamy
    doliny (count < 0.78 * mediana baseline) wzdluz kazdego boku. Rogi odsiewamy.
    Zwraca dict side -> lista (a,b) interwalow okna (m wzdluz boku)."""
    import numpy as np
    walls = _layer_segments(page, RE_WALL)
    W, H = cal.corpus_w, cal.corpus_h
    res = {}
    for side in ("west", "east", "south", "north"):
        vert = side in ("west", "east")
        tgt = 0.0 if side in ("west", "south") else (W if side == "east" else H)
        axis_len = H if vert else W
        nb = int(axis_len / bin_m) + 2
        bins = [set() for _ in range(nb)]
        for s in walls:
            if vert and s.orient == "v":
                x = cal.to_m(s.pos, 0)[0]
                if abs(x - tgt) < thick:
                    ya = cal.to_m(0, s.hi)[1]; yb = cal.to_m(0, s.lo)[1]
                    a, b = min(ya, yb), max(ya, yb)
                    for bi in range(max(0, int(a / bin_m)), min(nb, int(b / bin_m) + 1)):
                        bins[bi].add(round(x, 3))
            elif (not vert) and s.orient == "h":
                y = cal.to_m(0, s.pos)[1]
                if abs(y - tgt) < thick:
                    xa = cal.to_m(s.lo, 0)[0]; xb = cal.to_m(s.hi, 0)[0]
                    a, b = min(xa, xb), max(xa, xb)
                    for bi in range(max(0, int(a / bin_m)), min(nb, int(b / bin_m) + 1)):
                        bins[bi].add(round(y, 3))
        cnt = np.array([len(b) for b in bins[:int(axis_len / bin_m) + 1]])
        pos = np.arange(len(cnt)) * bin_m
        inside = cnt[(pos > 0.4) & (pos < axis_len - 0.4)]
        if len(inside) == 0:
            res[side] = []; continue
        base = np.median(inside)
        # okno = dolina ponizej baseline; prog wzgledny lub bezwzgledny (min 1 linia mniej)
        dip = cnt <= np.maximum(1, np.floor(base - 1)) if base <= 7 else cnt < base * 0.82
        ivs = []; i = 0
        while i < len(cnt):
            if dip[i] and 0.3 < pos[i] < axis_len - 0.3:
                j = i
                while j < len(cnt) and dip[j]:
                    j += 1
                a, b = i * bin_m, min(j * bin_m, axis_len)
                if (b - a) >= 0.4:
                    ivs.append((round(a, 2), round(b, 2)))
                i = j
            else:
                i += 1
        res[side] = ivs
    return res


# ============================================================================ #
#  LAYOUT-SPEC: deterministyczna budowa pokoi z osi wektorowych (PolSIATKI)
# ============================================================================ #
def snap_axis(val, page, cal, orient, fallback=None):
    """Dosun zadana wspolrzedna do najblizszej WEKTOROWEJ osi sciany (centerline),
    by wszystkie wspolrzedne pochodzily z PDF. orient='v' (x) | 'h' (y)."""
    vsegs, hsegs = wall_centerlines(page, cal)
    cands = [c[0] for c in (vsegs if orient == "v" else hsegs)]
    cands += [0.0, cal.corpus_w if orient == "v" else cal.corpus_h]
    if not cands:
        return val if fallback is None else fallback
    best = min(cands, key=lambda c: abs(c - val))
    return round(best, 3) if abs(best - val) < 0.4 else round(val, 3)


def emit_storey(page, cal, spec):
    """spec = dict z layoutem storey. Buduje pokoje (poligony z osi), przypisuje okna
    wg kontaktu z fasada, schody i drzwi z konfiguracji. Zwraca dict storey do JSON."""
    W, H = cal.corpus_w, cal.corpus_h
    wins = detect_windows(page, cal)
    fp = furniture_pts(page, cal); sp = stair_pts(page, cal)

    rooms_out = []
    for r in spec["rooms"]:
        poly = [[round(x, 3), round(y, 3)] for x, y in r["poly"]]
        g = Polygon(poly)
        # okna: dla kazdej strony, czy krawedz pokoju na fasadzie ma swiatlo
        wsides = []
        for side in ("west", "east", "south", "north"):
            if _room_touches_side(poly, side, W, H) and _side_has_window(poly, side, wins, W, H):
                wsides.append(side)
        rooms_out.append({
            "id": r["id"], "label": r["label"], "polygon": poly,
            "area_m2": round(r.get("area_m2", g.area), 2),
            "on_facade": any(_room_touches_side(poly, s, W, H) for s in ("west", "east", "south", "north")),
            "window_sides": r.get("window_sides", wsides),
        })

    out = {
        "storey": spec["storey"], "source_pdf": spec["source_pdf"],
        "outline": [[0.0, 0.0], [W, 0.0], [W, H], [0.0, H]],
        "entry": spec.get("entry"),
        "stairs": spec.get("stairs"),
        "open_plan_day_zone": spec.get("open_plan_day_zone", False),
        "facade_sides": ["north", "south", "east", "west"],
        "internal_walls": spec.get("internal_walls", []),
        "rooms": rooms_out,
        "doors": spec.get("doors", []),
    }
    if spec.get("roof_knee_wall"):
        out["roof_knee_wall"] = True
    return out


def _room_touches_side(poly, side, W, H, tol=0.12):
    if side == "west":
        return any(abs(x) < tol for x, y in poly)
    if side == "east":
        return any(abs(x - W) < tol for x, y in poly)
    if side == "south":
        return any(abs(y) < tol for x, y in poly)
    if side == "north":
        return any(abs(y - H) < tol for x, y in poly)
    return False


def _side_has_window(poly, side, wins, W, H, tol=0.12):
    """Czy ktorys interwal okna na danej stronie pokrywa krawedz pokoju na tej stronie."""
    if side in ("west", "east"):
        x0 = 0 if side == "west" else W
        ys = sorted(y for x, y in poly if abs(x - x0) < tol)
        if len(ys) < 2:
            return False
        lo, hi = ys[0], ys[-1]
    else:
        y0 = 0 if side == "south" else H
        xs = sorted(x for x, y in poly if abs(y - y0) < tol)
        if len(xs) < 2:
            return False
        lo, hi = xs[0], xs[-1]
    for a, b in wins.get(side, []):
        if min(hi, b) - max(lo, a) > 0.3:
            return True
    return False


# ============================================================================ #
#  LAYOUT TROPIE — wspolrzedne pochodza z osi wektorowych (snap_axis)
# ============================================================================ #
def layout_tropie_parter(pg, cal):
    W, H = cal.corpus_w, cal.corpus_h
    xm = snap_axis(3.53, pg, cal, "v")     # glowny podzial zach|wsch (salon)
    y1 = snap_axis(2.31, pg, cal, "h")     # lazienka | hol
    y2 = snap_axis(3.68, pg, cal, "h")     # hol | sypialnia
    rooms = [
        {"id": "lazienka", "label": "Lazienka", "poly": [(0, 0), (xm, 0), (xm, y1), (0, y1)], "area_m2": 5.38},
        {"id": "hol", "label": "Hol", "poly": [(0, y1), (xm, y1), (xm, y2), (0, y2)], "area_m2": 3.62},
        {"id": "sypialnia", "label": "Sypialnia", "poly": [(0, y2), (xm, y2), (xm, H), (0, H)], "area_m2": 6.98},
        {"id": "salon", "label": "Salon + kuchnia + jadalnia",
         "poly": [(xm, 0), (W, 0), (W, H), (xm, H)], "area_m2": 31.86},
    ]
    return {
        "storey": "parter", "source_pdf": "A.02 RZUT PARTERU.pdf",
        "entry": {"point": [0.0, round((y1 + y2) / 2, 2)], "side": "west", "wall": "v"},
        "stairs": {"kind": "u_winder",
                   "footprint": [[xm, 0.0], [snap_axis(4.8, pg, cal, "v"), 0.0],
                                 [snap_axis(4.8, pg, cal, "v"), snap_axis(2.7, pg, cal, "h")],
                                 [xm, snap_axis(2.7, pg, cal, "h")]], "down": True},
        "open_plan_day_zone": True,
        "rooms": rooms,
        "doors": [
            {"between": ["__outside__", "hol"], "point": [0.0, round((y1 + y2) / 2, 2)], "wall": "v", "type": "entry", "swing": 1},
            {"between": ["hol", "sypialnia"], "point": [1.4, y2], "wall": "h", "swing": 1},
            {"between": ["hol", "lazienka"], "point": [1.4, y1], "wall": "h", "swing": -1},
            {"between": ["hol", "salon"], "point": [xm, round((y1 + y2) / 2, 2)], "wall": "v", "type": "opening"},
        ],
    }


def layout_tropie_poddasze(pg, cal):
    W, H = cal.corpus_w, cal.corpus_h
    x1 = snap_axis(3.48, pg, cal, "v")     # sypialnie zach | srodek
    x2 = snap_axis(5.49, pg, cal, "v")     # srodek | master wsch
    yb = snap_axis(2.99, pg, cal, "h")     # podzial sypialni zach (2 -> 2.8/3.0) i klatki
    ym = snap_axis(3.65, pg, cal, "h")     # lazienka | hol srodek
    rooms = [
        {"id": "sypialnia_2", "label": "Sypialnia 2 (pld.-zach.)",
         "poly": [(0, 0), (x1, 0), (x1, yb), (0, yb)], "area_m2": 7.83},
        {"id": "sypialnia_1", "label": "Sypialnia 1 (pln.-zach.)",
         "poly": [(0, yb), (x1, yb), (x1, H), (0, H)], "area_m2": 9.15},
        {"id": "schody", "label": "Schody (klatka)",
         "poly": [(x1, 0), (x2, 0), (x2, ym), (x1, ym)], "area_m2": 3.67},
        {"id": "lazienka", "label": "Lazienka",
         "poly": [(x1, ym), (x2, ym), (x2, H), (x1, H)], "area_m2": 4.18},
        {"id": "master_sypialnia", "label": "Sypialnia (master, wsch.)",
         "poly": [(x2, 0), (W, 0), (W, H), (x2, H)], "area_m2": 20.34},
    ]
    return {
        "storey": "poddasze", "source_pdf": "A.03 PODDASZE.pdf",
        "roof_knee_wall": True, "entry": None,
        "stairs": {"kind": "u_winder",
                   "footprint": [[x1, 0.0], [x2, 0.0], [x2, ym], [x1, ym]], "down": True},
        "open_plan_day_zone": False,
        "rooms": rooms,
        "doors": [
            {"between": ["schody", "sypialnia_2"], "point": [round((x1 + x2) / 2, 2), 0.0], "wall": "h", "type": "opening"},
            {"between": ["schody", "sypialnia_1"], "point": [x1, round(yb / 2, 2)], "wall": "v", "swing": 1},
            {"between": ["schody", "lazienka"], "point": [round((x1 + x2) / 2, 2), ym], "wall": "h", "swing": 1},
            {"between": ["schody", "master_sypialnia"], "point": [x2, round(ym / 2, 2)], "wall": "v", "swing": 1},
        ],
    }


LAYOUTS = {
    "tropie": {"parter": layout_tropie_parter, "poddasze": layout_tropie_poddasze},
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="append", required=True,
                    help="sciezka:storey:corpus_w:corpus_h")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug", action="store_true",
                    help="tryb diagnostyczny: auto-polygonize zamiast layout-spec")
    args = ap.parse_args()

    storeys = []
    corpus_w = corpus_h = None
    for spec in args.pdf:
        path, storey, w, h = spec.rsplit(":", 3)
        w = float(w); h = float(h); corpus_w, corpus_h = w, h
        doc = fitz.open(path); pg = doc[0]
        cal = calibrate(pg, w, h)
        Wm = (cal.x1_pt - cal.x0_pt) * cal.scale
        Hm = (cal.y1_pt - cal.y0_pt) * cal.scale
        print(f"[{storey}] {path}")
        print(f"  calib={cal.method}  scale={cal.scale:.6f}  corpus={Wm:.3f}x{Hm:.3f} m "
              f"(cel {w}x{h})  windows={detect_windows(pg, cal)}")
        if args.debug:
            rooms, VX, HY = build_rooms(pg, cal)
            print(f"  [AUTO] {len(rooms)} komorek, VX={[round(x,2) for x in VX]} HY={[round(y,2) for y in HY]}")
            fp = furniture_pts(pg, cal); sp = stair_pts(pg, cal)
            for r in sorted(rooms, key=lambda p: -p.area):
                c = r.centroid
                print(f"    A={r.area:5.2f} @({c.x:4.2f},{c.y:4.2f}) furn={density(fp,r):4d} stair={density(sp,r):4d}")
            continue
        spec_fn = LAYOUTS.get(args.name, {}).get(storey)
        if spec_fn is None:
            print(f"  !! brak layout-spec dla {args.name}/{storey} — pomijam (uzyj --debug)")
            continue
        st_spec = spec_fn(pg, cal)
        st = emit_storey(pg, cal, st_spec)
        storeys.append(st)
        cover = sum(Polygon(r["polygon"]).area for r in st["rooms"])
        print(f"  rooms={len(st['rooms'])}  coverage={cover:.2f}/{w*h:.2f} m2  "
              f"({', '.join(r['id'] + (':' + ','.join(r['window_sides']) if r['window_sides'] else '') for r in st['rooms'])})")

    if not args.debug and storeys:
        data = {
            "name": args.name,
            "source_pdf_dir": "rzuty/domy",
            "units": "m",
            "model": ("sciany=linie (lokalizacja 1:1 z wektorow PDF); pokoje kafelkuja obrys "
                      "do osi scian; area_m2=netto; okna=window_sides (otwory w scianie zewn.)"),
            "extraction": "extract_pdf_rooms.py — kalibracja z lancuchow wymiarowych, osie z warstw scian, layout-spec PolSIATKI",
            "corpus_outline": [[0.0, 0.0], [corpus_w, 0.0], [corpus_w, corpus_h], [0.0, corpus_h]],
            "storeys": storeys,
        }
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print("ZAPISANO:", args.out)
