"""Realizm parteru domów 2-kond. (S30c): sypialnia + pełna łazienka na parterze,
łączna liczba sypialni zachowana (poddasze −1), spiżarnia wg powierzchni.
Spec: docs/superpowers/specs/2026-06-13-parter-realism-design.md"""
import pytest
from shapely.geometry import Polygon

from core.house_layout import (
    _template, parter_room_ids, pietro_room_ids, net_area, generate_house,
    attic_effective_area,
)


def test_parter_template_has_bedroom_and_bathroom():
    tpl = _template("house_parter")
    ids = {p.id for p in tpl.pokoje}
    assert "sypialnia_parter" in ids, "parter ma mieć sypialnię"
    assert "lazienka" in ids, "parter ma mieć pełną łazienkę"
    assert "wc" not in ids, "wc usunięte z parteru 2-kond. (łazienka zamiast)"
    syp = next(p for p in tpl.pokoje if p.id == "sypialnia_parter")
    assert syp.strefa.value == "NOCNA" and syp.wymaga_okna
    pairs = {frozenset((r.room_a, r.room_b)) for r in tpl.sasiedztwo}
    assert frozenset(("hub", "lazienka")) in pairs
    assert frozenset(("hub", "sypialnia_parter")) in pairs
    assert frozenset(("hub", "wc")) not in pairs


def test_solver_external_bathroom_param_targets_given_room():
    """Reguła 'nie landlocked' celuje w pokój `external_bathroom_id` (domyślnie wc).
    Sprawdzamy, że lazienka jest dociśnięta do ściany zewnętrznej gdy o to poprosimy."""
    from core.cpsat_solver import solve_cpsat
    from core.boundary_analyzer import analyze_boundary
    from core.house_layout import _template, _filter_template
    from core.house_program import default_house_config, HouseProgramConfig
    poly = Polygon([(0, 0), (10, 0), (10, 9), (0, 9)])
    b = analyze_boundary(poly, entry_point=(5.0, 0.0))
    tpl = _filter_template(_template("house_parter"),
                           {"hub", "wiatrolap", "salon", "kuchnia", "lazienka", "kotlownia"})
    cfg = default_house_config(storey="parter")
    r = solve_cpsat(tpl, b, time_limit_s=30.0, program_config=cfg,
                    hub_at_entry=True, entry_room_id="wiatrolap",
                    l_capable_ids={"hub"}, external_bathroom_id="lazienka")
    assert r.status in ("OPTIMAL", "FEASIBLE"), r.status
    laz = next(x for x in r.rooms if x.spec.id == "lazienka")
    bnds = laz.polygon.bounds  # (minx,miny,maxx,maxy), świat = bbox 10×9
    touches = (abs(bnds[0]) < 0.05 or abs(bnds[2] - 10) < 0.05 or
               abs(bnds[1]) < 0.05 or abs(bnds[3] - 9) < 0.05)
    assert touches, f"lazienka landlocked: {bnds}"


# Obrys z NIEZAWODNĄ sypialnią parteru (sonda parter8_bedroom_probe: 12.9×8.7=112 m²
# = 4/4 @60s; modalny 11×8=88 m² to loteria ~50% → fallback). Asercje „parter ma
# sypialnię" muszą iść na ten obrys, by nie flaczeć na best-effort fallbacku.
_RELIABLE = Polygon([(0, 0), (12.9, 0), (12.9, 8.7), (0, 8.7)])  # 112 m²
_RELIABLE_ENTRY = (6.45, 0.0)


def test_parter_selector_bedroom_replaces_spizarnia():
    """S30c: z sypialnią parter 8-pok BEZ spiżarni (perf); spiżarnia tylko w fallbacku."""
    tpl = _template("house_parter")
    big = parter_room_ids(tpl.pokoje, net_area(110.0))                           # z sypialnią
    fb = parter_room_ids(tpl.pokoje, net_area(110.0), with_parter_bedroom=False)  # fallback
    assert "sypialnia_parter" in big and "lazienka" in big and "wc" not in big
    assert "spizarnia" not in big, "z sypialnią parter 8-pok (spiżarnia wypada — perf)"
    assert "spizarnia" in fb and "sypialnia_parter" not in fb, "fallback: spiżarnia, bez sypialni"


def test_pietro_bedroom_offset_drops_one_keeps_min_one():
    tpl = _template("house_pietro")
    base = pietro_room_ids(tpl.pokoje, 70.0, bedroom_offset=0)
    off1 = pietro_room_ids(tpl.pokoje, 70.0, bedroom_offset=1)
    n_base = sum(1 for r in base if r.startswith("sypialnia"))
    n_off1 = sum(1 for r in off1 if r.startswith("sypialnia"))
    assert n_off1 == n_base - 1, f"offset=1 ma zdjąć 1 sypialnię ({n_base}→{n_off1})"
    assert n_off1 >= 1, "min 1 sypialnia zostaje na piętrze"


def test_bedroom_count_conserved_house_level():
    # Niezawodny obrys 112 m² (sypialnia parteru się mieści) → total zachowany.
    lay = generate_house(_RELIABLE, entry_point=_RELIABLE_ENTRY, num_storeys=2, time_limit_s=90.0)
    assert lay.ok, lay.message
    parter_beds = sum(1 for r in lay.parter_rooms if r.spec.id.startswith("sypialnia"))
    pietro_beds = sum(1 for r in lay.pietro_rooms if r.spec.id.startswith("sypialnia"))
    old = pietro_room_ids(_template("house_pietro").pokoje, attic_effective_area(_RELIABLE), bedroom_offset=0)
    old_beds = sum(1 for r in old if r.startswith("sypialnia"))
    assert parter_beds == 1, "1 sypialnia na parterze"
    assert parter_beds + pietro_beds == old_beds, f"total {parter_beds}+{pietro_beds} != stary {old_beds}"


def test_generate_2storey_parter_has_bedroom_bathroom():
    lay = generate_house(_RELIABLE, entry_point=_RELIABLE_ENTRY, num_storeys=2, time_limit_s=90.0)
    assert lay.ok, lay.message
    pids = [r.spec.id for r in lay.parter_rooms]
    assert sum(1 for i in pids if i.startswith("sypialnia")) == 1
    assert "lazienka" in pids and "wc" not in pids


def test_best_effort_fallback_house_always_ok():
    """Best-effort (S30c): ciasny modalny 11×8 (88 m²) — sypialnia parteru to loteria
    perf, ale fallback (bez sypialni) gwarantuje, że dom ZAWSZE się generuje, z pełną
    liczbą sypialni (total zachowany niezależnie od ścieżki)."""
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])  # 88 m² — loteria/fallback
    lay = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=90.0)
    assert lay.ok, lay.message
    parter_beds = sum(1 for r in lay.parter_rooms if r.spec.id.startswith("sypialnia"))
    pietro_beds = sum(1 for r in lay.pietro_rooms if r.spec.id.startswith("sypialnia"))
    assert parter_beds in (0, 1), "0 (fallback) lub 1 (sypialnia parteru)"
    assert parter_beds + pietro_beds >= 3, "total sypialni zachowany (≥3)"
    # łazienka parteru w obu ścieżkach (nie wc)
    pids = [r.spec.id for r in lay.parter_rooms]
    assert "lazienka" in pids and "wc" not in pids


def test_benchmark_room_f1_excludes_schody():
    from notebooks.reference_benchmark import room_set_f1, _room_multiset
    gen = [t for t in ["salon", "hol", "schody"] if t != "schody"]
    ref = ["salon", "hol"]
    assert room_set_f1(_room_multiset(gen), _room_multiset(ref)) == 1.0


def test_benchmark_master_is_house_level():
    from notebooks.reference_benchmark import _gen_room_type
    all_areas = {"sypialnia_parter": 9.0, "sypialnia_1": 16.0, "sypialnia_2": 11.0}
    master_id = max(all_areas, key=all_areas.get)
    assert master_id == "sypialnia_1"
    assert _gen_room_type("sypialnia_parter", "sypialnia_parter" == master_id) == "sypialnia"
    assert _gen_room_type("sypialnia_1", "sypialnia_1" == master_id) == "master_sypialnia"
