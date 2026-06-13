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


def test_parter_selector_always_bedroom_bathroom_spizarnia_gated():
    tpl = _template("house_parter")
    small = parter_room_ids(tpl.pokoje, net_area(63.0))    # ~51 netto
    big = parter_room_ids(tpl.pokoje, net_area(110.0))     # ~89 netto
    for s in (small, big):
        assert "sypialnia_parter" in s and "lazienka" in s
        assert "wc" not in s
    assert "spizarnia" not in small, "spiżarnia dopiero ≥60 netto"
    assert "spizarnia" in big
    no_bed = parter_room_ids(tpl.pokoje, net_area(110.0), with_parter_bedroom=False)
    assert "sypialnia_parter" not in no_bed
