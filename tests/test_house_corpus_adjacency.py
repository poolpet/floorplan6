"""Sąsiedztwa dużych parterów wg KORPUSU (S30, decyzja Dawida 2026-06-12).

Grunt: AR.02.1 (realny parter ~121 m², ekstrakcja S30 high-conf,
`notebooks/reference_plans_raw_partial.json`): hol 3.2 m² dotyka 4 pomieszczeń;
GARAŻ wchodzi przez PRZEDSIONEK (śluzę), nie przez hol; schowek/kuchnia przez
salon. Nasz szablon kazał holowi dotykać 7 pokoi (w tym garaż i kotłownię) —
to wymusza wielki L-hol i dusi solver (sonda `parter_adjacency_probe.py`).

Reguła: gdy parter MA garaż → hol↔garaż staje się garaż↔wiatrołap,
hol↔kotłownia staje się kotłownia↔garaż. Małe partery (bez garażu) BEZ ZMIAN
— kotłownia zostaje przy holu (jedyne wejście).
"""
from core.house_layout import (
    _corpus_parter_adjacency,
    _filter_template,
    _template,
    parter_template_for,
)


def _pairs(tpl):
    return {frozenset((r.room_a, r.room_b)) for r in tpl.sasiedztwo}


def _big_parter_tpl():
    # 157 m² gross (Tracja-klasa) → garaż + gabinet w zestawie
    return parter_template_for(157.0)


def test_big_parter_garage_enters_via_wiatrolap():
    pairs = _pairs(_big_parter_tpl())
    assert frozenset(("garaz", "wiatrolap")) in pairs, "garaż ma wchodzić przez wiatrołap-śluzę"
    assert frozenset(("hub", "garaz")) not in pairs, "hol nie musi dotykać garażu (korpus)"


def test_big_parter_kotlownia_via_garage():
    pairs = _pairs(_big_parter_tpl())
    assert frozenset(("kotlownia", "garaz")) in pairs, "kotłownia przez garaż (śluza techniczna)"
    assert frozenset(("hub", "kotlownia")) not in pairs


def test_big_parter_hub_keeps_core_star():
    pairs = _pairs(_big_parter_tpl())
    for rid in ("wiatrolap", "schody", "salon", "wc", "gabinet"):
        assert frozenset(("hub", rid)) in pairs, f"hol musi dotykać {rid}"
    # otwarta strefa dzienna + spiżarnia przy kuchni — bez zmian
    assert frozenset(("salon", "kuchnia")) in pairs
    assert frozenset(("kuchnia", "spizarnia")) in pairs
    # wejście do budynku bez zmian
    assert frozenset(("wiatrolap", "_outside")) in pairs


def test_small_parter_unchanged():
    # 63 m² gross → bez garażu/gabinetu → korpusowa przepisówka NIE dotyka reguł
    tpl = parter_template_for(63.0)
    pairs = _pairs(tpl)
    assert frozenset(("hub", "kotlownia")) in pairs, "bez garażu kotłownia zostaje przy holu"
    assert not any("garaz" in p for p in pairs)


def test_rewrite_is_identity_without_garage():
    base = _template("house_parter")
    small = _filter_template(base, {"hub", "schody", "wiatrolap", "salon",
                                    "kuchnia", "spizarnia", "wc", "kotlownia"})
    assert _pairs(_corpus_parter_adjacency(small)) == _pairs(small)
