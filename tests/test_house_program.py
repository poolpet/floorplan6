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


def test_salon_target_capped_not_inflated():
    """Na dużym obrysie salon NIE może urosnąć ponad cap (stary Q6 dawał ~46)."""
    specs = _parter_specs()
    cfg = HouseProgramConfig(caps=_house_caps())
    targets = compute_house_targets(specs, usable_area_m2=90.0, config=cfg)
    assert targets["salon"] <= 35.0 + 1e-6


def test_all_room_caps_respected():
    """Żaden pokój nie przekracza swojego cap-u, niezależnie od obrysu."""
    specs = _parter_specs() + [
        _spec("sypialnia_1", Strefa.NOCNA, 11.0, 14.0, (0.15, 0.25)),
        _spec("master", Strefa.NOCNA, 12.0, 16.0, (0.18, 0.28)),
    ]
    cfg = HouseProgramConfig(caps=_house_caps())
    targets = compute_house_targets(specs, usable_area_m2=120.0, config=cfg)
    assert targets["sypialnia_1"] <= 13.0 + 1e-6
    assert targets["master"] <= 16.5 + 1e-6
    assert targets["kuchnia"] <= 13.0 + 1e-6


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


def test_generate_house_no_room_bloat_realistic():
    """E2E: na realnym 9×7 (~63 m²/kondygn.) master ≤16.5 i salon ≤35 — stary
    kod pompował master do ~20 i salon na większych do ~47 (reguła Q6)."""
    from core.house_layout import generate_house
    poly = Polygon([(0, 0), (9, 0), (9, 7), (0, 7)])
    layout = generate_house(poly, entry_point=(4.5, 0.0), num_storeys=2, time_limit_s=25.0)
    assert layout.ok, layout.message
    by_id = {r.spec.id: r.area for r in (*layout.parter_rooms, *layout.pietro_rooms)}
    # master (sypialnia_1) i każda sypialnia nie puchną ponad cap ARCHON
    for rid, area in by_id.items():
        if rid == "sypialnia_1":
            assert area <= 16.5 + 0.3, f"master {area:.1f} > 16.5"
        elif rid.startswith("sypialnia"):
            assert area <= 13.0 + 0.5, f"{rid} {area:.1f} > 13"
        elif rid == "salon":
            assert area <= 35.0 + 0.5, f"salon {area:.1f} > 35"
