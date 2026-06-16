"""Korytarz: min szerokość 1.2 m (wyjątkowo 1.0 m) — reguła Dawida S31b.

Ramię L huba było ograniczone do ≥0.8 m (`cpsat_solver.py:466-467`), a baza pokoju
do ≥1.0 m (`:351`) → w renderach korytarz bywał za wąski „w jednym miejscu". Reguła:
KOMUNIKACJA (hol/podest/korytarz) ma najwęższe przewężenie ≥1.2 m domyślnie; gdy 1.2
czyni układ INFEASIBLE — ≥1.0 m (NIGDY poniżej).

Szerokość korytarza mierzona z polygonu (hub bywa L-kształtny = unia 2 prostokątów)
otwarciem morfologicznym: erozja+dylatacja promieniem r usuwa człony węższe niż 2r,
więc najmniejsze r gubiące istotne pole = połowa najwęższego przewężenia.
"""
import pytest
from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.template_selector import load_all_templates, select_templates


def corridor_min_width(poly, lo=0.2, hi=2.5, tol=0.005, area_eps=0.05):
    """Najwęższe przewężenie rektylinearnego polygonu [m] (otwarcie morfologiczne).

    Otwarcie promieniem r usuwa człony węższe niż 2r → próg r* (granica lo/hi)
    to połowa najwęższego przewężenia. Zwraca lo+hi (= 2·środek przedziału), żeby
    estymator był wycentrowany na progu (a nie systematycznie zaniżony o ~tol).
    Rozdzielczość ≈ tol → realne 1.20 m mierzy ~1.19-1.20 m.
    """
    full = poly.area

    def opened_loss(r):
        op = poly.buffer(-r, join_style="mitre").buffer(r, join_style="mitre")
        return full - op.area

    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if opened_loss(mid) > area_eps:
            hi = mid
        else:
            lo = mid
    return lo + hi


APT44_W, APT44_H = 5.58, 7.88


def _solve_apt44(entry_frac=0.18):
    poly = Polygon([(0, 0), (APT44_W, 0), (APT44_W, APT44_H), (0, APT44_H)])
    boundary = analyze_boundary(poly, (APT44_W * entry_frac, 0.0))
    template = select_templates("M2", boundary, load_all_templates())[0]
    return solve_cpsat(template, boundary, time_limit_s=25.0)


def _hub(result):
    return next(r for r in result.rooms if r.spec.strefa.value == "KOMUNIKACJA")


def test_house_corridor_fallback_keeps_generating():
    """Dom, który nie zdąży z korytarzem 1.2 m (probe: 11×8 @1.2 wolne >45 s) i tak się
    generuje — fast-fail 1.2 m (krótki budżet) → fallback 1.0 m (reguła Dawida „wyjątkowo",
    pełny budżet, @1.0 OPTIMAL ~56 s). Korytarz holu nigdy <1.0 m. Bez fallbacku ten dom
    = UNKNOWN w budżecie (regresja S31b: 1.0 m sam trudniejszy niż stare 0.8 m)."""
    from core.house_layout import generate_house
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])
    lay = generate_house(poly, (5.5, 0.0), num_storeys=2, time_limit_s=90.0)
    assert lay.ok, lay.message
    hub = next(r for r in lay.parter_rooms if r.spec.strefa.value == "KOMUNIKACJA")
    w = corridor_min_width(hub.polygon)
    assert w >= 1.0 - 0.02, f"korytarz parteru {w:.2f} m < 1.0 m (hard floor)"


def test_apt44_hub_corridor_min_width_default():
    """Najwęższe przewężenie holu ≥1.2 m (domyślny korytarz, NIE 0.8 m ramię L).

    apt-44 to najciaśniejszy modalny obrys (lider rynku M2); 1.2 m okazuje się
    FEASIBLE bez fallbacku. Próg z tolerancją 2 cm na dyskretyzację helpera
    (ograniczenie wymusza dokładnie 120 cm; pre-fix mierzyło 0.89 m).
    """
    result = _solve_apt44()
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    w = corridor_min_width(_hub(result).polygon)
    assert w >= 1.20 - 0.02, f"korytarz holu {w:.2f} m < 1.2 m"
