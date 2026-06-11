"""Poddasze KNEE-WALL v2 (S29, decyzja Dawida po przeglądzie rzutów S27/28):
poddasze ma PEŁNY footprint parteru, ale wzdłuż DŁUŻSZYCH krawędzi biegną strefy
NISKIEJ ścianki kolankowej. Reguły:
  - układ: żaden pokój piętra nie może być W CAŁOŚCI w strefie niskiej,
  - meble: wysokie (szafa/regały/kocioł) poza strefą niską; niskie (łóżko, WC,
    wanna) mogą w niej stać,
  - schody/piony jak w S27 (bieg prosty wzdłuż kalenicy, L-podest).
Zastępuje model „pas przy kalenicy" z S27 (pokrycie piętra znów == pełny obrys).
"""
import pytest
from shapely.geometry import Polygon, box

from core.house_layout import (
    ATTIC_LOW_STRIP_FACTOR,
    attic_low_strips,
    generate_house,
)


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


# ---------------------------------------------------------------------------
# Geometria stref niskich (czyste, bez CP-SAT)
# ---------------------------------------------------------------------------

def test_low_strips_along_longer_edges():
    strips = attic_low_strips(_rect(12, 8))   # kalenica wzdłuż X → strefy przy y=0 i y=H
    assert len(strips) == 2
    depth = ATTIC_LOW_STRIP_FACTOR * 8
    s_low = next(s for s in strips if s.bounds[1] == 0.0)
    s_high = next(s for s in strips if s.bounds[3] == 8.0)
    assert s_low.bounds == (0.0, 0.0, 12.0, pytest.approx(depth))
    assert s_high.bounds == (0.0, pytest.approx(8 - depth), 12.0, 8.0)


def test_low_strips_vertical_ridge():
    strips = attic_low_strips(_rect(8, 12))   # kalenica wzdłuż Y → strefy przy x=0 i x=W
    depth = ATTIC_LOW_STRIP_FACTOR * 8
    xs = sorted(s.bounds for s in strips)
    assert xs[0] == (0.0, 0.0, pytest.approx(depth), 12.0)
    assert xs[1] == (pytest.approx(8 - depth), 0.0, 8.0, 12.0)


def test_low_strips_world_coords_non_origin():
    strips = attic_low_strips(Polygon([(100, 50), (112, 50), (112, 58), (100, 58)]))
    depth = ATTIC_LOW_STRIP_FACTOR * 8
    s_low = next(s for s in strips if s.bounds[1] == 50.0)
    assert s_low.bounds == (100.0, 50.0, 112.0, pytest.approx(50 + depth))


# ---------------------------------------------------------------------------
# Integracja generate_house (CP-SAT)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lay_11x8():
    lay = generate_house(_rect(11, 8), entry_point=(5.5, 0.0), time_limit_s=60.0)
    assert lay.ok, lay.message
    return lay


def test_pietro_covers_full_footprint_again(lay_11x8):
    """Model S29: poddasze = pełny obrys (== parter), nie pas."""
    total = sum(r.polygon.area for r in lay_11x8.pietro_rooms)
    assert abs(total - 88.0) < 1e-3
    assert lay_11x8.attic_boundary is None          # pas z S27 wycofany
    assert len(lay_11x8.attic_low_strips) == 2      # strefy niskie obecne


def test_no_pietro_room_fully_inside_low_strip(lay_11x8):
    """Pokój w całości pod skosem (wys. < ~1.9 m wszędzie) byłby bezużyteczny."""
    for r in lay_11x8.pietro_rooms:
        for strip in lay_11x8.attic_low_strips:
            assert not r.polygon.within(strip.buffer(1e-6)), \
                f"{r.spec.id} w całości w strefie niskiej {strip.bounds}"


def test_stairs_vertically_aligned(lay_11x8):
    sp = _room(lay_11x8.parter_rooms, "schody")
    sg = _room(lay_11x8.pietro_rooms, "schody")
    assert sp is not None and sg is not None
    for a, b in zip(sp.polygon.bounds, sg.polygon.bounds):
        assert a == pytest.approx(b, abs=0.02)


def test_two_storey_63m2_generates_again():
    """Bramka pasa z S27 (min ~76 m²) zniesiona — realne domy 60-76 m² z poddaszem
    wracają do gry (wzorzec A.01.2/3: dom 68.7 m² Z poddaszem istnieje)."""
    lay = generate_house(_rect(9, 7), entry_point=(4.5, 0.0), time_limit_s=60.0)
    assert lay.ok, lay.message
    assert sum(r.polygon.area for r in lay.pietro_rooms) == pytest.approx(63.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Meble: wysokie poza strefą niską, niskie dozwolone
# ---------------------------------------------------------------------------

def test_tall_furniture_avoids_low_strips(lay_11x8):
    from core.furniture import TALL_TYPES, furnish_rooms
    fr = furnish_rooms(lay_11x8.pietro_rooms, boundary=lay_11x8.boundary,
                       low_zones=lay_11x8.attic_low_strips)
    placed_tall = [f for f in fr.furniture if f.piece_type in TALL_TYPES]
    for f in placed_tall:
        for strip in lay_11x8.attic_low_strips:
            inter = f.polygon.intersection(strip).area
            assert inter < 1e-6, \
                f"{f.piece_type} w {f.room_id} wchodzi w strefę niską ({inter:.2f} m²)"


def test_low_furniture_allowed_in_strips_unit():
    """Łóżko POD SKOSEM jest dozwolone (klasyka poddasza) — strefa niska nie
    blokuje mebli niskich."""
    from core.furniture import TALL_TYPES
    assert "bed" not in TALL_TYPES
    assert "toilet" not in TALL_TYPES
    assert "bathtub" not in TALL_TYPES   # wanna niska; prysznic = wysoki, ale
    assert "wardrobe" in TALL_TYPES      # piece 'bathtub' renderujemy jako wannę
    assert "shelving" in TALL_TYPES


# ---------------------------------------------------------------------------
# Render / preview / kontrakt
# ---------------------------------------------------------------------------

def test_render_details_contract_with_low_strips(lay_11x8, tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from core.plan_contract import house_to_contract
    from viz.house_preview import house_details_text, render_house_figure

    p = tmp_path / "kneewall.png"
    render_house_figure(lay_11x8, with_furniture=True, save_path=p, show=False)
    assert p.exists() and p.stat().st_size > 0
    txt = house_details_text(lay_11x8)
    assert "poddasze" in txt.lower()

    c = house_to_contract(lay_11x8)
    got = c["poddasze"]["meta"]["boundary_bbox"]      # poddasze = pełny obrys
    for a, b in zip(got, (0.0, 0.0, 11.0, 8.0)):
        assert a == pytest.approx(b, abs=1e-3)
    strips = c["poddasze"]["meta"]["attic_low_strips"]  # strefy w kontrakcie (C++/AC)
    assert len(strips) == 2
