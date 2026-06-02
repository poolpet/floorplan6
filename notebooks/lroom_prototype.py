"""Faza 2b prototyp — mechanika opcjonalnego 2. prostokąta (L-pokój) w CP-SAT.

Izolowany test: mała plansza, kilka pokoi prostokątnych + JEDEN L-capable ('hol'),
który MUSI być L (wymuszamy by dotykał 2 rooms w przeciwnych rogach, czego prostokąt
≤cap nie da). Sprawdza: presence literal + NoOverlap2D(optional) + ciągłość 2 rects +
pokrycie sumujące obecne pola. Cel: zwalidować mechanikę zanim wejdzie do solvera.
"""
from ortools.sat.python import cp_model

SCALE = 100
W, H = 600, 600  # cm (6x6 m)


def build(force_L: bool):
    m = cp_model.CpModel()
    # 4 pokoje: A,B w przeciwnych rogach (wymuszone), C wypełniacz, hol (L-capable).
    # Chcemy by hol dotykał A (lewy-dół) i B (prawy-góra) — prostokąt nie-spine tego nie da,
    # więc hol musi być L (ramię w poziomie + ramię w pionie).
    rooms = {}

    def rect(name, optional=False, presence=None):
        x = m.new_int_var(0, W, f"x_{name}")
        y = m.new_int_var(0, H, f"y_{name}")
        w = m.new_int_var(0 if optional else 80, W, f"w_{name}")
        h = m.new_int_var(0 if optional else 80, H, f"h_{name}")
        xe = m.new_int_var(0, W, f"xe_{name}"); m.add(xe == x + w)
        ye = m.new_int_var(0, H, f"ye_{name}"); m.add(ye == y + h)
        if optional:
            xi = m.new_optional_interval_var(x, w, xe, presence, f"xi_{name}")
            yi = m.new_optional_interval_var(y, h, ye, presence, f"yi_{name}")
        else:
            xi = m.new_interval_var(x, w, xe, f"xi_{name}")
            yi = m.new_interval_var(y, h, ye, f"yi_{name}")
        return dict(x=x, y=y, w=w, h=h, xe=xe, ye=ye, xi=xi, yi=yi)

    # primary rects
    A = rect("A"); B = rect("B"); C = rect("C"); hol1 = rect("hol1")
    has_L = m.new_bool_var("has_L")
    hol2 = rect("hol2", optional=True, presence=has_L)

    if not force_L:
        m.add(has_L == 0)
        m.add(hol2["w"] == 0); m.add(hol2["h"] == 0)

    xivs = [A["xi"], B["xi"], C["xi"], hol1["xi"], hol2["xi"]]
    yivs = [A["yi"], B["yi"], C["yi"], hol1["yi"], hol2["yi"]]
    m.add_no_overlap_2d(xivs, yivs)

    # A w lewym-dolnym rogu, B w prawym-górnym (wymuszone narożniki)
    m.add(A["x"] == 0); m.add(A["y"] == 0); m.add(A["w"] == 200); m.add(A["h"] == 200)
    m.add(B["xe"] == W); m.add(B["ye"] == H); m.add(B["w"] == 200); m.add(B["h"] == 200)

    from core.cpsat_solver import _touches_bool
    # ciągłość: gdy has_L, hol2 współdzieli krawędź z hol1 (zreifikowane sąsiedztwo)
    t_contig = _touches_bool(m, hol1["x"], hol1["y"], hol1["xe"], hol1["ye"],
                             hol2["x"], hol2["y"], hol2["xe"], hol2["ye"], 80, W, H, "contig")
    m.add(t_contig == 1).only_enforce_if(has_L)
    # sąsiedztwo PRZEZ KTÓRYKOLWIEK prostokąt: A musi dotykać holu (rect1 LUB rect2)
    tA1 = _touches_bool(m, A["x"], A["y"], A["xe"], A["ye"],
                        hol1["x"], hol1["y"], hol1["xe"], hol1["ye"], 80, W, H, "A_hol1")
    tA2 = _touches_bool(m, A["x"], A["y"], A["xe"], A["ye"],
                        hol2["x"], hol2["y"], hol2["xe"], hol2["ye"], 80, W, H, "A_hol2")
    m.add(tA2 == 0).only_enforce_if(has_L.Not())  # nie przez nieobecny rect
    m.add_bool_or([tA1, tA2])

    # pole efektywne hol2 (0 gdy brak L)
    a1 = m.new_int_var(0, W * H, "a1"); m.add_multiplication_equality(a1, [hol1["w"], hol1["h"]])
    a2 = m.new_int_var(0, W * H, "a2"); m.add_multiplication_equality(a2, [hol2["w"], hol2["h"]])
    ea2 = m.new_int_var(0, W * H, "ea2")
    m.add(ea2 == a2).only_enforce_if(has_L)
    m.add(ea2 == 0).only_enforce_if(has_L.Not())
    aA = 200 * 200; aB = 200 * 200
    aC = m.new_int_var(0, W * H, "aC"); m.add_multiplication_equality(aC, [C["w"], C["h"]])
    # pokrycie: A+B+C+hol1+ea2 == W*H
    m.add(aA + aB + aC + a1 + ea2 == W * H)

    return m, dict(A=A, B=B, C=C, hol1=hol1, hol2=hol2, has_L=has_L, ea2=ea2, a1=a1)


def solve(force_L):
    m, v = build(force_L)
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = 8
    st = s.solve(m)
    name = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE", cp_model.UNKNOWN: "UNKNOWN"}[st]
    print(f"force_L={force_L}: {name}", end="")
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        hl = s.value(v["has_L"])
        h1 = (s.value(v["hol1"]["x"]), s.value(v["hol1"]["y"]), s.value(v["hol1"]["w"]), s.value(v["hol1"]["h"]))
        h2 = (s.value(v["hol2"]["x"]), s.value(v["hol2"]["y"]), s.value(v["hol2"]["w"]), s.value(v["hol2"]["h"]))
        print(f"  has_L={hl} hol1={h1} hol2={h2} ea2={s.value(v['ea2'])}")
    else:
        print()


if __name__ == "__main__":
    solve(force_L=False)  # bez L — powinien działać (hol prostokąt)
    solve(force_L=True)   # z L — hol2 obecny, ciągły, pokrycie sumuje oba ramiona
