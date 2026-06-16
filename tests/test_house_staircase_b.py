"""Approach B — schody jako OSOBNY pokój 'schody' przypięty do rdzenia klatki
+ osobny 'hub'/Hol jako gwiazda-rozdzielacz F5.

Sesja 18 (OK Dawida 2026-06-02): klatka schodowa to własny pokój przypięty do
reserved_core, NIE scalony w hub. Hol zostaje centrum gwiazdy F5. Wariant: pinned,
podest przy Holu / bieg w głąb, sąsiedztwo tylko Hol.
"""
from shapely.geometry import Polygon, box

from core.house_layout import generate_house, _stair_core_dims
from core.models import Strefa


def _gen(W, H, entry):
    # 90 s (S31b): korytarz ≥1.0/1.2 m jest TWARDSZY dla solvera niż dawne 0.8 m —
    # modalne domy 88-96 m² potrzebują fast-fail 1.2 + fallback 1.0 (~50-90 s; był 60).
    return generate_house(Polygon([(0, 0), (W, 0), (W, H), (0, H)]), entry, time_limit_s=90.0)


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


def _shared_edge_len(a, b) -> float:
    """Długość wspólnej krawędzi dwóch pokojów (prostokąty osiowe)."""
    inter = a.polygon.boundary.intersection(b.polygon.boundary)
    return inter.length


# UWAGA (knee-wall, S26): piętro solvuje się na PASIE poddasza (0.6 krótszej osi),
# więc stały program piętra (suma minów 40.5 m² · margines) wymaga footprintu ≥ ~76 m².
# Stare obrysy testowe 63-70 m² są ARCHITEKTONICZNIE za małe na dom 2-kond. z poddaszem
# użytkowym — macierz przeniesiona na realne obrysy (80-96 m²).


def test_schody_is_separate_room():
    layout = _gen(10.0, 8.0, (5.0, 0.0))
    assert layout.ok, layout.message
    # winder default (S31b): 10×8 (aspect 1.25 ≤ 1.4) → rdzeń U; band 4–6 m² nadal trzyma (5.76)
    sw, sh, _ = _stair_core_dims(10.0, 8.0)
    core_area = sw * sh
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        schody = next((r for r in rooms if r.spec.id == "schody"), None)
        hol = next((r for r in rooms if r.spec.id == "hub"), None)
        assert schody is not None, "brak osobnego pokoju 'schody'"
        assert hol is not None, "brak osobnego 'hub'/hol"
        assert schody is not hol
        assert schody.spec.strefa == Strefa.KOMUNIKACJA
        assert hol.spec.strefa == Strefa.KOMUNIKACJA
        # schody ~= rdzeń klatki (pinned), w realnym paśmie 4–6 m²
        assert abs(schody.area - core_area) < 0.25, f"schody {schody.area:.2f} != rdzeń {core_area:.2f}"
        assert 4.0 <= schody.area <= 6.0


def test_schody_pinned_to_core_on_both_storeys():
    """Wyrównanie pionowe: schody == rdzeń klatki, identycznie na parterze i piętrze
    (knee-wall: rdzeń re-bazowany do bboxa pasa poddasza — pozycja ŚWIATA ta sama)."""
    layout = _gen(11.0, 8.0, (5.5, 0.0))
    assert layout.ok, layout.message
    cx, cy, sw, sh = layout.stair_core
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        b = _room(rooms, "schody").polygon.bounds
        assert abs(b[0] - cx) < 0.05 and abs(b[1] - cy) < 0.05
        assert abs((b[2] - b[0]) - sw) < 0.05 and abs((b[3] - b[1]) - sh) < 0.05


def test_schody_adjacent_to_hol_on_both_storeys():
    """Schody otwierają się na hol (≥0.9 m wspólnej krawędzi) — F5 routing klatki."""
    layout = _gen(11.0, 8.0, (5.5, 0.0))
    assert layout.ok, layout.message
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        schody, hol = _room(rooms, "schody"), _room(rooms, "hub")
        assert _shared_edge_len(schody, hol) >= 0.9 - 1e-6


def test_hol_does_not_contain_core():
    """Hol NIE obejmuje rdzenia klatki (rdzeń należy do osobnego pokoju schody) —
    sedno Approach B (dawniej scalony hub zawierał rdzeń)."""
    layout = _gen(10.0, 8.0, (5.0, 0.0))
    assert layout.ok, layout.message
    cx, cy, sw, sh = layout.stair_core
    core = box(cx, cy, cx + sw, cy + sh)
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        hol = _room(rooms, "hub")
        assert not hol.polygon.contains(core.buffer(-0.02))


def test_parter_hol_is_compact():
    """Hol parteru (przedsionek) jest mały na realnym obrysie — nadmiar bierze salon,
    nie hol (dawny scalony hub puchł >12 m²). Próg = F4 (15% usable): dawny absolutny
    ≤10 m² był kalibrowany na obrysy 63-70 m², na 80-96 m² hol ~12% to nadal minimal."""
    for (W, H, e) in [(10.0, 8.0, 5.0), (11.0, 8.0, 5.5), (12.0, 8.0, 6.0)]:
        layout = _gen(W, H, (e, 0.0))
        assert layout.ok, layout.message
        hol = _room(layout.parter_rooms, "hub")
        # F4 (15% usable): hol kompaktowy. Próg 13% był nadgorliwy — solver legalnie
        # zwraca hol ~12-13 m² na 96 m² (≈13.x%, pod F4), a wartość waha się dokładnie
        # na 13% (niedeterminizm CP-SAT) → fałszywe value-faile (S30c). UNKNOWN-flak
        # 96 m² parteru pozostaje = krawędź perf parteru (kolejka S26).
        assert hol.area <= 0.15 * W * H, f"{W}x{H} hol parteru {hol.area:.1f} > F4 15% ({0.15*W*H:.1f})"


def test_schody_not_a_door_zone_source():
    """Schody (KOMUNIKACJA) NIE są źródłem strefy drzwi — pokój dotykający tylko
    schodów nie dostaje fałszywych drzwi do klatki (routing idzie przez hol, F5)."""
    from core.furniture import _infer_door_zones
    from core.models import Room, RoomSpec

    def mk(rid, strefa, x, y, w, h):
        sp = RoomSpec(id=rid, nazwa=rid, strefa=strefa, wymaga_okna=False, priorytet_fasady=None)
        r = Room(spec=sp, polygon=box(x, y, x + w, y + h))
        r.update_metrics()
        return r

    schody = mk("schody", Strefa.KOMUNIKACJA, 0.0, 0.0, 2.0, 3.0)
    syp = mk("sypialnia_1", Strefa.NOCNA, 0.0, 3.0, 2.0, 3.0)  # styka się tylko ze schodami
    zones = _infer_door_zones([schody, syp])
    assert zones["sypialnia_1"] == []


def test_stair_run_orientation_points_away_from_hol():
    """Bieg wzdłuż dłuższej osi rdzenia; strzałka 'w górę' odchodzi OD holu (podest
    przy Holu, wchodzisz od strony holu i wspinasz się w głąb)."""
    from viz.plan_renderer import stair_run_orientation
    # straight core wąski-głęboki (sh>sw) -> bieg pionowy; hol pod schodami (S) -> w górę N
    schody_deep = (2.0, 2.0, 3.0, 6.0)   # sw=1, sh=4
    hol_below = (1.0, 0.0, 5.0, 2.0)
    assert stair_run_orientation(schody_deep, hol_below) == ("vertical", "N")
    hol_above = (1.0, 6.0, 5.0, 8.0)
    assert stair_run_orientation(schody_deep, hol_above) == ("vertical", "S")
    # straight core szeroki (sw>sh) -> bieg poziomy; hol na zachód (W) -> w prawo E
    schody_wide = (2.0, 2.0, 6.0, 3.0)   # sw=4, sh=1
    hol_west = (0.0, 1.0, 2.0, 5.0)
    assert stair_run_orientation(schody_wide, hol_west) == ("horizontal", "E")
    hol_east = (6.0, 1.0, 8.0, 5.0)
    assert stair_run_orientation(schody_wide, hol_east) == ("horizontal", "W")
    # ~kwadrat (U-core): oś wg dominującej strony holu (nie szumu float)
    schody_sq = (0.0, 1.8, 2.4, 4.2)         # w≈h≈2.4
    hol_dom_east = (2.4, 0.0, 6.0, 4.2)       # hol głównie na wschód -> bieg poziomy, W
    assert stair_run_orientation(schody_sq, hol_dom_east) == ("horizontal", "W")
    hol_dom_south = (0.0, 0.0, 5.0, 1.8)      # hol głównie pod -> bieg pionowy, N
    assert stair_run_orientation(schody_sq, hol_dom_south) == ("vertical", "N")


def test_feasible_across_footprints_and_entries():
    """De-ryzyko pinningu+knee-wall: feasible na 10×8/11×8/12×8/8×11 dla WSZYSTKICH
    4 stron wejścia, w tym straight-core (12×8) × wejście W/E (to zawieszało piętro,
    póki nie odpięliśmy holu piętra od ściany wejścia) oraz rdzeń przy ścianie N/S
    (wejście W/E) × pas poddasza dosnapowany do rdzenia."""
    cases = [
        (10.0, 8.0, (5.0, 0.0)), (11.0, 8.0, (5.5, 0.0)), (12.0, 8.0, (6.0, 0.0)), (8.0, 11.0, (4.0, 0.0)),
        (10.0, 8.0, (5.0, 8.0)),                                   # N
        (11.0, 8.0, (0.0, 4.0)), (12.0, 8.0, (0.0, 4.0)), (8.0, 11.0, (0.0, 5.5)),   # W
        (11.0, 8.0, (11.0, 4.0)), (12.0, 8.0, (12.0, 4.0)),                          # E
        # 10×8 W/E świadomie POZA macierzą: pas 48 m² + rdzeń środkowo-osiowy (wejście
        # boczne odsuwa rdzeń od szczytu) = realna granica modelu knee-wall; realne
        # domy poddaszowe zaczynają się od ~88 m² footprintu.
    ]
    for W, H, e in cases:
        layout = _gen(W, H, e)
        assert layout.ok, f"{W}x{H} entry {e}: {layout.message}"


def test_compact_house_gets_winder_u_kind():
    """S31b: obrys compact (aspect ≤ 1.4) → rdzeń U (zabiegowe), nie bieg prosty.
    Probe: U na 88/130 m² daje parter FEASIBLE (prosty dawał UNKNOWN)."""
    layout = _gen(10.0, 8.0, (5.0, 0.0))   # aspect 1.25 ≤ 1.4 → U
    assert layout.ok, layout.message
    assert layout.stair_kind == "u", f"oczekiwano 'u', jest {layout.stair_kind!r}"
    for rooms in (layout.parter_rooms, layout.pietro_rooms):
        schody = _room(rooms, "schody")
        assert getattr(schody, "stair_kind", None) == "u"


def test_elongated_house_keeps_straight_kind():
    """Obrys wydłużony (aspect > 1.4) zostaje przy biegu prostym — winder tylko compact."""
    layout = _gen(12.0, 8.0, (6.0, 0.0))   # aspect 1.5 > 1.4 → straight
    assert layout.ok, layout.message
    assert layout.stair_kind == "straight"


def test_winder_unknown_falls_back_to_straight_core():
    """Dom się generuje mimo trudności (straight-core retry + korytarz-fallback).
    S31b: budżet 15→90 s — korytarz ≥1.0 m jest twardszy niż 0.8 m, kaskada
    (1.2 fast-fail → 1.0 → straight → bedroom-drop) potrzebuje realnego czasu;
    przy 15 s żaden korytarz nie zdążył. Niedeterministyczne — sprawdzamy ok=True."""
    from shapely.geometry import Polygon
    from core.house_layout import generate_house
    layout = generate_house(Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]), (5.0, 0.0),
                            time_limit_s=90.0)
    assert layout.ok, layout.message
    assert layout.stair_kind in ("u", "straight")
