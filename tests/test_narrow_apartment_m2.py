"""Wąskie mieszkanie 2-pok (M2) — lider rynku ~40% sprzedaży (archon.pl).

Lokal karmiony korytarzem budynku: krótki bok ~5.6 m, głębokość ~7.9 m, wejście na
KRÓTKIEJ ścianie. Prostokątny hol musi sięgnąć od salonu (góra) do łazienki/sypialni
(dół) → rozdyma się do ~24% (>F4 15%), a przy wejściu w CENTRUM krótkiej ściany staje
się INFEASIBLE. Naprawa (decyzja Dawida S26 — "mini-korytarz"): hol L-kształtny dla
wąskich mieszkań (auto `l_capable` hub) — cienki L owija łazienkę i dotyka wszystkich
pokoi mniejszym polem (~14%), i jest feasible niezależnie od pozycji drzwi.

Patrz `core/cpsat_solver.py` (narrow_apt → l_capable hub).
"""
import pytest
from shapely.geometry import Polygon

from core.boundary_analyzer import analyze_boundary
from core.cpsat_solver import solve_cpsat
from core.template_selector import load_all_templates, select_templates

# apt-44 "2-pok kompaktowe" — najpopularniejszy obrys (archon.pl suite).
APT44_W, APT44_H = 5.58, 7.88
APT44_AREA = APT44_W * APT44_H  # ~44 m²


def _m2_template():
    return [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]


def _solve_apt44(entry_x):
    poly = Polygon([(0, 0), (APT44_W, 0), (APT44_W, APT44_H), (0, APT44_H)])
    boundary = analyze_boundary(poly, (entry_x, 0.0))
    template = select_templates("M2", boundary, load_all_templates())[0]
    return solve_cpsat(template, boundary, time_limit_s=25.0), template


@pytest.mark.parametrize("entry_frac,label", [
    (0.5, "wejscie-w-CENTRUM krotkiej sciany"),
    (0.18, "wejscie off-center (realny lokal z korytarza)"),
    (0.05, "wejscie w rogu"),
])
def test_apt44_m2_feasible_any_entry(entry_frac, label):
    """Wąski 2-pok jest feasible niezależnie od pozycji drzwi na krótkiej ścianie."""
    result, template = _solve_apt44(APT44_W * entry_frac)
    assert result.status in ("OPTIMAL", "FEASIBLE"), \
        f"apt-44 M2 INFEASIBLE dla {label}"
    assert len(result.rooms) == len(template.pokoje) == 4


def test_apt44_m2_full_coverage():
    """F1 — pokrycie 100% obrysu (suma pól == usable, łącznie z 2. prostokątem L)."""
    result, _ = _solve_apt44(APT44_W * 0.18)
    total = sum(r.polygon.area for r in result.rooms)
    assert abs(total - APT44_AREA) < 0.1, f"coverage {total:.2f} != {APT44_AREA:.2f}"


def test_apt44_m2_hub_slim_corridor():
    """Hol szczupły (≤16% usable) — L-korytarz, NIE rozdęty prostokąt 24%."""
    result, _ = _solve_apt44(APT44_W * 0.18)
    hub = next(r for r in result.rooms if r.spec.strefa.value == "KOMUNIKACJA")
    pct = hub.polygon.area / APT44_AREA * 100
    assert pct <= 16.0, f"hol {pct:.0f}% usable — za gruby (cel: szczupły L-korytarz ≤16%)"


def test_apt44_m2_is_two_room():
    """To 2-pok: dokładnie 1 sypialnia + salon z aneksem (NIE downgrade do kawalerki)."""
    result, _ = _solve_apt44(APT44_W * 0.18)
    n_syp = sum(1 for r in result.rooms if "sypial" in r.spec.id)
    assert n_syp == 1, f"oczekiwano 1 sypialni (2-pok), jest {n_syp}"
    assert any("salon" in r.spec.id for r in result.rooms)


def test_apt44_m2_hub_touches_all_rooms():
    """F5 — hol (nawet L-kształtny) dotyka każdego pokoju wspólną krawędzią ≥0.5 m."""
    result, _ = _solve_apt44(APT44_W * 0.18)
    hub = next(r for r in result.rooms if r.spec.strefa.value == "KOMUNIKACJA")
    for room in result.rooms:
        if room.spec.strefa.value == "KOMUNIKACJA":
            continue
        shared = hub.polygon.intersection(room.polygon).length
        assert shared >= 0.5, f"hol nie dotyka {room.spec.id}: shared={shared:.2f}m"
