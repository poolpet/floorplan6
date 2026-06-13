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
