"""Bloat/capy domu — pure (bez CP-SAT)."""
from core.house_program import DEFAULT_HOUSE_CAPS


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
