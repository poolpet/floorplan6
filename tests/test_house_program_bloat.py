"""Bloat/capy domu — pure (bez CP-SAT)."""
from core.house_program import DEFAULT_HOUSE_CAPS
from core.house_program import compute_house_targets, default_house_config
from core.models import RoomSpec, Strefa


def _spec(rid, strefa, minp, pct):
    return RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False,
                    priorytet_fasady=None, min_powierzchnia=minp,
                    procent_powierzchni=pct)


def test_garaz_cap_matches_reference_median():
    # ref garaz median 32.7, min 21.5 — cap 22 był PONIŻEJ ref-min (gwarantowany MAPE)
    assert DEFAULT_HOUSE_CAPS["garaz"] >= 33.0


def test_schody_cap_matches_winder_footprint():
    # ref schody median 5.6 obu kondygnacji — cap 5.0 under-sizował klatkę
    assert DEFAULT_HOUSE_CAPS["schody"] >= 6.0


def test_master_cap_near_geomedian():
    # geoMed master 17.76; cap 16.5 → 17.0 kompromis wiążący
    assert DEFAULT_HOUSE_CAPS["master"] >= 17.0


def test_kotlownia_cap_covers_upper_half():
    # ref kotlownia max 12.6, median 7.8 — cap 8.0 klipował górę
    assert DEFAULT_HOUSE_CAPS["kotlownia"] >= 9.0


def test_overflow_preserves_day_zone_cap_and_routes_to_night_dry():
    """S31b D4: nadmiar F1 NIE wraca w strefę dzienną (open-plan invariant), NIE w mokre;
    sucha usługowa (kotłownia) absorbuje. F1 zachowane."""
    specs = [
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, (0.04, 0.08)),
        _spec("salon", Strefa.DZIENNA, 18.0, (0.20, 0.30)),
        _spec("kuchnia", Strefa.DZIENNA, 8.0, (0.08, 0.12)),
        _spec("sypialnia_1", Strefa.NOCNA, 9.0, (0.10, 0.16)),
        _spec("gabinet", Strefa.NOCNA, 9.0, (0.09, 0.15)),
        _spec("kotlownia", Strefa.USLUGOWA, 5.0, (0.04, 0.07)),
        _spec("lazienka", Strefa.USLUGOWA, 4.0, (0.04, 0.07)),
    ]
    cfg = default_house_config(storey="parter")
    t = compute_house_targets(specs, 120.0, cfg)
    assert abs(sum(t.values()) - 120.0) < 1e-6                           # F1 zachowane
    assert t["salon"] + t["kuchnia"] <= cfg.day_zone_cap(120.0) + 1e-6   # day-cap invariant
    assert t["lazienka"] <= 5.0 + 1e-6                                   # mokra nie rośnie (WT)
    assert t["kotlownia"] >= t["lazienka"]                              # sucha usługowa może absorbować


def test_overflow_preserves_f1_pure_bedroom_attic():
    """Czysto-sypialniane poddasze: F1 zachowane; mokra capowana. (Pełny anty-bloat sypialni
    wymaga densyfikacji — odłożone; tu pilnujemy niezmienników.)"""
    specs = [
        _spec("hub", Strefa.KOMUNIKACJA, 4.0, (0.05, 0.10)),
        _spec("sypialnia_1", Strefa.NOCNA, 10.0, (0.14, 0.22)),
        _spec("sypialnia_2", Strefa.NOCNA, 10.0, (0.14, 0.22)),
        _spec("sypialnia_3", Strefa.NOCNA, 9.0, (0.12, 0.18)),
        _spec("garderoba", Strefa.USLUGOWA, 3.0, (0.03, 0.06)),
        _spec("lazienka", Strefa.USLUGOWA, 5.0, (0.06, 0.10)),
    ]
    cfg = default_house_config(storey="poddasze", master_id="sypialnia_1")
    t = compute_house_targets(specs, 95.0, cfg)
    assert abs(sum(t.values()) - 95.0) < 1e-6
    assert t["lazienka"] <= 8.0 + 1e-6                                   # poddasze łazienka cap
    assert t["garderoba"] >= 3.0                                         # sucha usługowa absorbuje część
