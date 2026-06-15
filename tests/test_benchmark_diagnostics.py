"""Diagnostyki benchmarku — pure helpery (bez CP-SAT, szybkie)."""
from notebooks.reference_benchmark import stair_kind_match


def test_stair_match_winder_2storey():
    r = stair_kind_match("u", has_schody=True, storeys=2, ref_kind="u_winder")
    assert r["gen"] == "u_winder" and r["match"] == 1.0


def test_stair_mismatch_straight_vs_winder():
    r = stair_kind_match("straight", has_schody=True, storeys=2, ref_kind="u_winder")
    assert r["gen"] == "straight" and r["match"] == 0.0


def test_stair_single_storey_is_none():
    r = stair_kind_match("straight", has_schody=False, storeys=1, ref_kind="none")
    assert r["gen"] == "none" and r["match"] == 1.0


def test_stair_winder_matches_winder_ref():
    assert stair_kind_match("u", True, 2, "u_winder")["match"] == 1.0
    assert stair_kind_match("u", True, 2, "straight")["match"] == 0.0
