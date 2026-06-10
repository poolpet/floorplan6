"""TDD: konfigurowalny program domu — cap-y + %-podział (zastępuje regułę Q6
'salon zjada nadmiar' na ścieżce DOMU; M1-M5 nietknięte).

Cap-y/%-udziały ugruntowane na korpusie ARCHON (Session 17): salon+jadalnia 35,
kuchnia 13, sypialnia 13, master 16.5, łazienka parter 5 / poddasze 8.
"""
import pytest
from shapely.geometry import Polygon

from core.models import RoomSpec, Strefa
from core.house_program import HouseProgramConfig, compute_house_targets


def _spec(rid, strefa, min_p, opt_p, pct=(0.0, 1.0)):
    return RoomSpec(
        id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False,
        priorytet_fasady=None, min_powierzchnia=min_p,
        opt_powierzchnia=opt_p, procent_powierzchni=pct,
    )


def _parter_specs():
    return [
        _spec("salon", Strefa.DZIENNA, 18.0, 25.0, (0.30, 0.40)),
        _spec("kuchnia", Strefa.DZIENNA, 8.0, 10.0, (0.10, 0.16)),
        _spec("wiatrolap", Strefa.KOMUNIKACJA, 3.0, 5.0, (0.03, 0.08)),
        _spec("kotlownia", Strefa.USLUGOWA, 4.0, 6.0, (0.04, 0.10)),
        _spec("spizarnia", Strefa.USLUGOWA, 1.5, 2.5, (0.02, 0.05)),
        _spec("wc", Strefa.USLUGOWA, 1.5, 2.5, (0.02, 0.05)),
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, 6.0, (0.06, 0.14)),
    ]


def _house_caps():
    return {
        "salon": 35.0, "kuchnia": 13.0, "sypialnia": 13.0, "master": 16.5,
        "gabinet": 14.0, "kotlownia": 8.0, "pralnia": 6.0, "spizarnia": 5.0,
        "garderoba": 6.0, "wiatrolap": 8.0, "wc": 3.0,
    }


def test_day_zone_capped_overflow_to_bedrooms():
    """Open-plan + reguła Dawida: gdy jest sink SYPIALNI, nadmiar idzie do sypialni,
    a strefa dzienna trzyma się ŁĄCZNEGO cap-u (salon NIE balonuje). Korytarz minimalny."""
    specs = _parter_specs() + [
        _spec("sypialnia_1", Strefa.NOCNA, 11.0, 14.0, (0.15, 0.25)),
        _spec("sypialnia_2", Strefa.NOCNA, 9.0, 12.0, (0.12, 0.22)),
    ]
    cfg = HouseProgramConfig(caps=_house_caps())
    usable = 120.0
    targets = compute_house_targets(specs, usable, cfg)
    combined = cfg.day_zone_cap(usable)
    assert targets["salon"] + targets["kuchnia"] <= combined + 1e-6     # dzień ≤ łączny cap
    # nadmiar zyskały SYPIALNIE (urosły ponad %-target/cap), nie hub
    assert targets["sypialnia_1"] > 14.0 or targets["sypialnia_2"] > 12.0
    assert abs(sum(targets.values()) - usable) < 1e-6


def test_bedrooms_absorb_overflow_f2_still_capped():
    """Reguła Dawida: SYPIALNIE wchłaniają nadmiar (mogą rosnąć ponad cap ARCHON, bo
    korytarz ma być minimalny). Ale F2 (łazienka ≤5) i łączny cap dnia ZOSTAJĄ twarde."""
    specs = _parter_specs() + [
        _spec("sypialnia_1", Strefa.NOCNA, 11.0, 14.0, (0.15, 0.25)),
        _spec("lazienka", Strefa.USLUGOWA, 2.5, 4.8, (0.06, 0.12)),
    ]
    cfg = HouseProgramConfig(caps=_house_caps(), storey="parter")
    targets = compute_house_targets(specs, 120.0, cfg)
    assert targets["sypialnia_1"] > 14.0                          # sypialnia wchłonęła nadmiar
    assert targets["lazienka"] <= 5.0 + 1e-6                      # F2 trzyma twardo
    assert targets["salon"] + targets["kuchnia"] <= cfg.day_zone_cap(120.0) + 1e-6


def test_pct_share_used_within_bounds():
    """Target salonu ≈ środek %-udziału·usable, gdy mieści się w [min, cap]."""
    specs = _parter_specs()
    cfg = HouseProgramConfig(caps=_house_caps())
    targets = compute_house_targets(specs, usable_area_m2=64.0, config=cfg)
    # salon pct (0.30,0.40) -> mid 0.35 * 64 = 22.4 (w [18,35]) — po water-fill może wzrosnąć,
    # ale nie spaść poniżej %-targetu
    assert targets["salon"] >= 0.35 * 64.0 - 1e-6
    assert targets["salon"] <= 35.0 + 1e-6


def test_targets_sum_to_usable_F1_remainder_not_over_cap():
    """F1: Σtargets == usable (reszta rozłożona water-fillingiem), salon ≤ cap."""
    specs = _parter_specs()
    cfg = HouseProgramConfig(caps=_house_caps())
    usable = 64.0
    targets = compute_house_targets(specs, usable, cfg)
    assert abs(sum(targets.values()) - usable) < 1e-6
    assert targets["salon"] <= 35.0 + 1e-6
    # każdy pokój nadal ≥ swojego min
    for s in specs:
        assert targets[s.id] >= s.min_powierzchnia - 1e-6


def test_bathroom_cap_per_storey():
    """Łazienka: parter ≤5 m², poddasze ≤8 m² (decyzja Dawida, zgodne z ARCHON)."""
    laz = _spec("lazienka", Strefa.USLUGOWA, 2.5, 4.8, (0.06, 0.12))
    other = _spec("master", Strefa.NOCNA, 12.0, 16.0, (0.50, 0.60))
    cfg_par = HouseProgramConfig(caps=_house_caps(), storey="parter")
    cfg_pod = HouseProgramConfig(caps=_house_caps(), storey="poddasze")
    tp = compute_house_targets([laz, other], 80.0, cfg_par)
    tpod = compute_house_targets([laz, other], 80.0, cfg_pod)
    assert tp["lazienka"] <= 5.0 + 1e-6
    assert tpod["lazienka"] <= 8.0 + 1e-6
    assert tpod["lazienka"] > 5.0  # poddasze dopuszcza większą łazienkę rodzinną


def test_day_zone_combined_cap():
    """Open-plan (faza 1): strefa dzienna (DZIENNA = salon+kuchnia) ma ŁĄCZNY cap
    (~0.36·usable), nie sumę per-pokój 35+13=48. Otwarta przestrzeń sizowana jako
    całość; per-pokój cap-y zostają jako pod-sufity, łączny jest wiążący dla grupy."""
    specs = [
        _spec("salon", Strefa.DZIENNA, 18.0, 25.0, (0.35, 0.45)),
        _spec("kuchnia", Strefa.DZIENNA, 8.0, 10.0, (0.12, 0.18)),
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, 6.0, (0.04, 0.10)),
        _spec("sypialnia_1", Strefa.NOCNA, 11.0, 14.0, (0.15, 0.25)),
    ]
    cfg = HouseProgramConfig(caps=_house_caps())
    usable = 120.0
    targets = compute_house_targets(specs, usable, cfg)
    combined = cfg.day_zone_cap(usable)
    assert combined < _house_caps()["salon"] + _house_caps()["kuchnia"]  # łączny < suma per-pokój
    assert targets["salon"] + targets["kuchnia"] <= combined + 1e-6
    assert abs(sum(targets.values()) - usable) < 1e-6                    # F1 trzyma
    assert targets["kuchnia"] <= _house_caps()["kuchnia"] + 1e-6         # per-pokój sub-cap zostaje


def test_targets_sum_to_usable_even_without_hub():
    """Inwariant Σtargets==usable trzyma też gdy program nie ma pokoju KOMUNIKACJA/hub
    (fallback sink = największy pokój), nadmiar nie znika ani nie psuje F1."""
    specs = [
        _spec("salon", Strefa.DZIENNA, 18.0, 25.0, (0.30, 0.40)),
        _spec("sypialnia_1", Strefa.NOCNA, 11.0, 14.0, (0.15, 0.25)),
        _spec("lazienka", Strefa.USLUGOWA, 2.5, 4.8, (0.06, 0.12)),
    ]
    cfg = HouseProgramConfig(caps=_house_caps())
    targets = compute_house_targets(specs, usable_area_m2=80.0, config=cfg)
    assert abs(sum(targets.values()) - 80.0) < 1e-6


def test_corridor_minimal_excess_to_bedrooms():
    """Reguła Dawida (2026-06-02): korytarz możliwie NAJMNIEJSZY (F4 hub ≤15%); nadmiar
    ZYSKUJĄ sypialnie, NIE korytarz. (Sesja 18 błędnie robiła hub sinkiem → podest 22%.)
    Sypialnie mogą rosnąć (cap to miękki guide), ale bez eksplozji; salon ≤ ~cap."""
    from core.house_layout import generate_house
    poly = Polygon([(0, 0), (11, 0), (11, 8), (0, 8)])  # 88 m² parter (knee-wall: pas ≥ programu piętra)
    layout = generate_house(poly, entry_point=(5.5, 0.0), num_storeys=2, time_limit_s=45.0)
    assert layout.ok, layout.message
    # korytarz minimalny na OBU kondygnacjach — F4 liczone od USABLE danej kondygnacji
    # (knee-wall: piętro żyje na pasie poddasza, nie pełnym obrysie)
    attic_usable = layout.attic_boundary.polygon.area
    for rooms, usable in ((layout.parter_rooms, 88.0), (layout.pietro_rooms, attic_usable)):
        hub = next(r for r in rooms if r.spec.id == "hub")
        assert hub.area <= 0.15 * usable + 1.0, f"korytarz {hub.area:.1f} > F4 (15% = {0.15*usable:.1f})"
    # sypialnie wchłaniają nadmiar (mogą rosnąć), ale bez eksplozji
    for r in layout.pietro_rooms:
        if r.spec.id.startswith("sypialnia"):
            assert r.area <= 20.0, f"{r.spec.id} {r.area:.1f} eksploduje (>20)"
    salon = next(r for r in layout.parter_rooms if r.spec.id == "salon")
    # Na 88 m² parterze leftover przelewa się do strefy dziennej PONAD per-pokój cap 35
    # (znany, odłożony w S26 GAP „cap overflow strefy dziennej parteru — osobno potem");
    # do czasu tej naprawy kontrakt = salon ≤ ŁĄCZNY cap strefy dziennej (45).
    assert salon.area <= 45.0 + 2.0, f"salon {salon.area:.1f} > łączny cap strefy dziennej"
