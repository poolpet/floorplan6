"""Diagnostyki benchmarku — pure helpery (bez CP-SAT, szybkie)."""
from shapely.geometry import box

from notebooks.reference_benchmark import room_iou, stair_kind_match


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


def test_room_iou_identical_is_one():
    g = [("salon", box(0, 0, 4, 3))]
    r = [("salon", box(0, 0, 4, 3))]
    assert abs(room_iou(g, r) - 1.0) < 1e-6


def test_room_iou_half_overlap():
    # ref [0,4]x[0,2]=8; gen [2,6]x[0,2]=8; przecięcie [2,4]x[0,2]=4; unia=12 → 1/3
    g = [("salon", box(2, 0, 6, 2))]
    r = [("salon", box(0, 0, 4, 2))]
    assert abs(room_iou(g, r) - (4.0 / 12.0)) < 1e-6


def test_room_iou_no_matching_type_is_none():
    g = [("kuchnia", box(0, 0, 4, 3))]
    r = [("salon", box(0, 0, 4, 3))]
    assert room_iou(g, r) is None
