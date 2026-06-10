"""Knee-wall poddasze (S26): piętro solvowane na PASIE użytkowym przy kalenicy,
nie na pełnym obrysie.

Model (decyzja Dawida, S26): poddasze użytkowe = pas o pełnej długości wzdłuż
kalenicy (dłuższa oś obrysu) × ATTIC_BAND_FACTOR krótszej osi, wycentrowany,
przesunięty minimalnie tak, by zawierał rdzeń schodów; przycięty do obrysu.
Parter bez zmian (pełny obrys). Schody pionowo wyrównane między kondygnacjami.
"""
import pytest
from shapely.geometry import Polygon, box

from core.house_layout import (
    ATTIC_BAND_FACTOR,
    _attic_band_polygon,
    _reserve_core,
    generate_house,
)


def _rect(w: float, h: float) -> Polygon:
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


# ---------------------------------------------------------------------------
# Geometria pasa (czyste, bez CP-SAT)
# ---------------------------------------------------------------------------

def test_attic_band_factor_in_decided_range():
    # Decyzja S26: pas użytkowy = ~0.55-0.65 krótszej osi obrysu.
    assert 0.55 <= ATTIC_BAND_FACTOR <= 0.65


def test_attic_band_full_length_no_uncoverable_sliver():
    poly = _rect(12, 8)
    core = _reserve_core(poly.bounds, (6.0, 0.0), force_straight=True)  # wejście S, rdzeń y∈[1.8, 2.9]
    band = _attic_band_polygon(poly, core)
    minx, miny, maxx, maxy = band.bounds
    assert (minx, maxx) == (0.0, 12.0)  # pełna długość wzdłuż kalenicy (dłuższa oś = X)
    assert maxy - miny == pytest.approx(ATTIC_BAND_FACTOR * 8, abs=1e-6)
    # Wycentrowany pas [1.6, 6.4] zostawiałby 0.2 m szczelinę pas↔rdzeń — przy F1 (==)
    # niepokrywalną (min_szerokosc pokoi ≥1.0, prostokąt nad nią blokują pinned schody)
    # → krawędź pasa dosnapowana do krawędzi rdzenia: pas [1.8, 6.6].
    assert miny == pytest.approx(core[1], abs=1e-6)
    # niezmiennik: szczelina pas↔rdzeń wzdłuż osi pasa = 0 albo ≥ szerokość pokoju
    for gap in (core[1] - miny, maxy - (core[1] + core[3])):
        assert gap < 1e-9 or gap >= 1.5 - 1e-9
    assert band.within(poly.buffer(1e-9))


def test_attic_band_shifts_to_contain_stair_core():
    poly = _rect(12, 8)
    # wejście E nisko → rdzeń przy ścianie N (poza wycentrowanym pasem)
    core = _reserve_core(poly.bounds, (12.0, 2.0), force_straight=True)
    band = _attic_band_polygon(poly, core)
    cx, cy, cw, ch = core
    assert box(cx, cy, cx + cw, cy + ch).within(band.buffer(1e-9))
    assert band.bounds[3] - band.bounds[1] == pytest.approx(ATTIC_BAND_FACTOR * 8, abs=1e-6)
    assert band.within(poly.buffer(1e-9))


def test_attic_band_ridge_along_longer_axis_vertical():
    poly = _rect(8, 12)  # dłuższa oś = Y → kalenica pionowa, pas ogranicza X
    core = _reserve_core(poly.bounds, (4.0, 0.0), force_straight=True)
    band = _attic_band_polygon(poly, core)
    minx, miny, maxx, maxy = band.bounds
    assert (miny, maxy) == (0.0, 12.0)
    assert maxx - minx == pytest.approx(ATTIC_BAND_FACTOR * 8, abs=1e-6)
    cx, cy, cw, ch = core
    assert box(cx, cy, cx + cw, cy + ch).within(band.buffer(1e-9))


def test_attic_band_north_entry_snaps_upper_gap():
    # Wejście N → rdzeń cofnięty od ściany N (y∈[5.1, 6.2]); wycentrowany pas [1.6, 6.4]
    # zostawiałby 0.2 m szczelinę NAD rdzeniem (gap_hi) → snap górnej krawędzi pasa
    # do górnej krawędzi rdzenia: pas [1.4, 6.2].
    poly = _rect(12, 8)
    core = _reserve_core(poly.bounds, (6.0, 8.0), force_straight=True)
    band = _attic_band_polygon(poly, core)
    minx, miny, maxx, maxy = band.bounds
    assert maxy == pytest.approx(core[1] + core[3], abs=1e-6)
    assert maxy - miny == pytest.approx(ATTIC_BAND_FACTOR * 8, abs=1e-6)
    assert box(core[0], core[1], core[0] + core[2], core[1] + core[3]).within(band.buffer(1e-9))
    assert band.within(poly.buffer(1e-9))


def test_attic_band_world_coords_non_origin_footprint():
    # Obrysy z AC NIE zaczynają się w (0,0) — pas i zawieranie rdzenia liczone w świecie.
    poly = Polygon([(100, 50), (112, 50), (112, 58), (100, 58)])
    core = _reserve_core(poly.bounds, (106.0, 50.0), force_straight=True)  # bbox-relative
    band = _attic_band_polygon(poly, core)
    minx, miny, maxx, maxy = band.bounds
    assert (minx, maxx) == (100.0, 112.0)
    assert maxy - miny == pytest.approx(ATTIC_BAND_FACTOR * 8, abs=1e-6)
    # rdzeń (bbox-relative) przeniesiony do świata musi być w pasie
    wx, wy = 100 + core[0], 50 + core[1]
    assert box(wx, wy, wx + core[2], wy + core[3]).within(band.buffer(1e-9))
    assert band.within(poly.buffer(1e-9))


def test_attic_band_clipped_to_l_footprint():
    # L-kształt: prostokąt 14×10 z wycięciem 6×4 w rogu NE
    poly = Polygon([(0, 0), (14, 0), (14, 6), (8, 6), (8, 10), (0, 10)])
    core = _reserve_core(poly.bounds, (7.0, 0.0), force_straight=True)
    band = _attic_band_polygon(poly, core)
    assert band.within(poly.buffer(1e-9))      # pas NIE wystaje poza obrys
    assert band.area > 0
    # pas to przecięcie pasma bbox z obrysem → nie szerszy niż factor·krótsza oś
    assert band.bounds[3] - band.bounds[1] <= ATTIC_BAND_FACTOR * 10 + 1e-9


# ---------------------------------------------------------------------------
# Integracja generate_house (CP-SAT)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lay_11x8():
    lay = generate_house(_rect(11, 8), entry_point=(5.5, 0.0), time_limit_s=45.0)
    assert lay.ok, lay.message
    return lay


def test_generate_house_pietro_covers_attic_band_not_full(lay_11x8):
    ab = lay_11x8.attic_boundary
    assert ab is not None
    attic_area = ab.polygon.area
    assert attic_area == pytest.approx(ATTIC_BAND_FACTOR * 88.0, rel=1e-6)
    total = sum(r.polygon.area for r in lay_11x8.pietro_rooms)
    assert abs(total - attic_area) < 1e-3  # F1 (==) na PASIE poddasza
    for r in lay_11x8.pietro_rooms:
        assert r.polygon.within(ab.polygon.buffer(1e-6)), \
            f"{r.spec.id} wystaje poza pas poddasza"


def test_generate_house_parter_still_covers_full_footprint(lay_11x8):
    total = sum(r.polygon.area for r in lay_11x8.parter_rooms)
    assert abs(total - 88.0) < 1e-3


def test_stairs_vertically_aligned_with_attic(lay_11x8):
    sp = _room(lay_11x8.parter_rooms, "schody")
    sg = _room(lay_11x8.pietro_rooms, "schody")
    assert sp is not None and sg is not None
    for a, b in zip(sp.polygon.bounds, sg.polygon.bounds):
        assert a == pytest.approx(b, abs=0.02)


def test_attic_too_small_returns_clear_message():
    # 9×7 = 63 m² → pas 0.6 → ~37.8 m² < suma minów programu piętra (40.5 m²).
    lay = generate_house(_rect(9, 7), entry_point=(4.5, 0.0), time_limit_s=20.0)
    assert not lay.ok
    assert "poddasze" in lay.message.lower()


# ---------------------------------------------------------------------------
# Render / preview (różne footprinty per panel)
# ---------------------------------------------------------------------------

def test_house_contract_poddasze_uses_attic_boundary(lay_11x8):
    """Kontrakt JSON (skorupa C++/GUI): poddasze raportuje bbox/okna z PASA poddasza,
    nie z pełnego obrysu parteru (bez fixa boundary_bbox==(0,0,11,8) zamiast pasa)."""
    from core.plan_contract import house_to_contract
    c = house_to_contract(lay_11x8)
    ab = lay_11x8.attic_boundary.polygon.bounds
    got = c["poddasze"]["meta"]["boundary_bbox"]
    for a, b in zip(got, ab):
        assert a == pytest.approx(b, abs=1e-3)


def test_render_and_details_with_attic(lay_11x8, tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from viz.house_preview import house_details_text, render_house_figure

    p = tmp_path / "attic.png"
    render_house_figure(lay_11x8, with_furniture=True, save_path=p, show=False)
    assert p.exists() and p.stat().st_size > 0
    txt = house_details_text(lay_11x8)
    assert "poddasze" in txt.lower()  # raport rozróżnia kondygnacje o różnych powierzchniach
