"""RED-first: cap salonu mieszkaniowego (salon_aneks) w _compute_target_areas.

Bez capa: salon = min + 0.8*excess → gigant (84 m² na 124 m²; render Dawida 2026-06-09).
Z capem: salon ≤ cap, nadmiar przepychany do sypialni. Dotyczy TYLKO mieszkań
(domy mają osobny compute_house_targets). Suma targetów dalej == usable (F1).
"""
import math

from core.cpsat_solver import _compute_target_areas, APARTMENT_DAY_ZONE_CAP
from core.models import RoomSpec, Strefa


def _spec(id, strefa, mn, opt=None):
    return RoomSpec(id=id, nazwa=id, strefa=strefa, wymaga_okna=False,
                    priorytet_fasady=None, min_powierzchnia=mn,
                    opt_powierzchnia=opt if opt is not None else mn)


def _m3_specs():
    return [
        _spec("hub", Strefa.KOMUNIKACJA, 5.0, 8.1),
        _spec("lazienka", Strefa.USLUGOWA, 2.5, 4.0),
        _spec("sypialnia_1", Strefa.NOCNA, 9.0, 12.0),
        _spec("sypialnia_2", Strefa.NOCNA, 6.0, 9.0),
        _spec("salon_aneks", Strefa.DZIENNA, 16.0, 24.0),
    ]


def test_salon_aneks_capped_on_large_apartment():
    targets = _compute_target_areas(_m3_specs(), 124.0)
    assert targets["salon_aneks"] <= APARTMENT_DAY_ZONE_CAP + 1e-6   # nie gigant 84
    # nadmiar poszedł do sypialni (więcej niż min)
    assert targets["sypialnia_1"] > 9.0
    assert targets["sypialnia_2"] > 6.0


def test_capped_targets_still_sum_to_usable():
    usable = 124.0
    targets = _compute_target_areas(_m3_specs(), usable)
    assert abs(sum(targets.values()) - usable) < 1e-6              # F1


def test_small_apartment_salon_below_cap_unchanged():
    # małe mieszkanie: salon poniżej capa → rozkład Q6 bez zmian
    targets = _compute_target_areas(_m3_specs(), 50.0)
    assert targets["salon_aneks"] < APARTMENT_DAY_ZONE_CAP


def test_suggest_mtype_scales_with_area():
    # Dobór typu wg powierzchni: większe mieszkanie = więcej sypialni
    # (M1=0, M2=1, M3=2, M4=3, M5=4 sypialnie). 124 m² → M4 (3 syp., uwaga Dawida).
    from core.template_selector import suggest_mtype
    assert suggest_mtype(30) == "M1"
    assert suggest_mtype(45) == "M2"
    assert suggest_mtype(65) == "M3"
    assert suggest_mtype(95) == "M4"
    assert suggest_mtype(124) == "M4"
    assert suggest_mtype(150) == "M5"
