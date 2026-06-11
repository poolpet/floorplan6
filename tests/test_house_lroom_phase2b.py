"""Faza 2b — natywne pokoje L-capable (hol parteru). Strażniki NOWYCH inwariantów,
których istniejący suite NIE pokrywa:
  1. WC dotyka ściany ZEWNĘTRZNEJ (bug Dawida #1) — i to bez rozdęcia holu (≤F4).
  2. Wiatrołap dotyka ściany WEJŚCIA (bug Dawida #2).
  3. WC↔hol i wiatrołap↔hol ≥0.9 m mimo owinięcia ramieniem L (F5, _apply_adjacency).
  4. Pełne F1 z aktywnym L: pokrycie == usable ORAZ brak nakładania pokoi.
  5. Hol-L = jeden spójny Polygon (nie rozłączny MultiPolygon).
  6. WC pozostaje prostokątem (nie jest L-capable); F2 caps niezmienione.
  7. Mieszkania M1-M5 (l_capable_ids falsy) — no-op modelu (deterministycznie, przez proto).

Feasibility-matrix i hol-compact-na-realnym-obrysie SĄ JUŻ pokryte
(test_house_staircase_b.test_feasible_across_footprints_and_entries / test_parter_hol_is_compact,
test_house_program.test_corridor_minimal_excess_to_bedrooms) — tu NIE dublujemy, dokładamy
per-stronę-wejścia asercje POZYCJI (WC/wiatrołap) sprzężone z F4-cap parteru.

UWAGA: asercje dopasowane do REALNEGO kontraktu modelu (zweryfikowane w cpsat_solver.py):
nie-spine = bok holu ≤ max(0.6·B, 0.8·min(BW,BH)). W modelu NIE MA ograniczenia aspect≤1.5
ani twardego 60% — nie asertujemy progów, których kod nie obiecuje.
"""
import pytest
from shapely.geometry import Polygon

from core.cpsat_solver import solve_cpsat
from core.house_layout import generate_house

SIDES = ["south", "north", "west", "east"]


def _entry(side, W, H):
    return {"south": (W / 2, 0.0), "north": (W / 2, H),
            "west": (0.0, H / 2), "east": (W, H / 2)}[side]


_CACHE = {}


def _layout(W, H, side, t=45.0):
    """Generuje (i cache'uje) układ — ten sam (W,H,side) nie jest solvowany dwa razy."""
    key = (W, H, side)
    if key not in _CACHE:
        poly = Polygon([(0, 0), (W, 0), (W, H), (0, H)])
        _CACHE[key] = generate_house(poly, _entry(side, W, H), num_storeys=2, time_limit_s=t)
    return _CACHE[key]


def _room(rooms, rid):
    return next((r for r in rooms if r.spec.id == rid), None)


def _touches_any_wall(b, W, H, tol=0.05):
    return (abs(b[0]) < tol or abs(b[2] - W) < tol or
            abs(b[1]) < tol or abs(b[3] - H) < tol)


def _shared(a, b):
    return a.polygon.boundary.intersection(b.polygon.boundary).length


# --- 1. WC przy ścianie zewnętrznej + hol parteru kompaktowy (sprzężenie = sedno fazy 2b) ---
@pytest.mark.parametrize("side", SIDES)
def test_wc_external_and_parter_hol_compact(side):
    """Bug Dawida #1: WC dotyka ściany ZEWNĘTRZNEJ (nie landlocked w środku) — i to BEZ
    rozdęcia korytarza: hol parteru ≤ F4 (15%). To dokładnie konflikt, który faza 2b
    rozwiązuje L-holem (prostokątny model rozdymał hol >15%, stąd rewert).
    Obrys 11×8 (88 m²): knee-wall (S26) wymaga pasa poddasza ≥ programu piętra."""
    W, H = 11.0, 8.0
    lay = _layout(W, H, side)
    assert lay.ok, f"{W}x{H} {side}: {lay.message}"
    wc = _room(lay.parter_rooms, "wc")
    assert wc is not None
    assert _touches_any_wall(wc.polygon.bounds, W, H), \
        f"WC landlocked ({side}): bounds={wc.polygon.bounds}"
    hub = _room(lay.parter_rooms, "hub")
    usable = W * H
    assert hub.area <= 0.15 * usable + 1.0, \
        f"hol parteru {hub.area:.1f} > F4 ({0.15 * usable:.1f}) [{side}]"


# --- 2. Wiatrołap przy ścianie wejścia ---
@pytest.mark.parametrize("side", SIDES)
def test_wiatrolap_on_entry_wall(side):
    """Bug Dawida #2: wiatrołap (śluza wejściowa) dotyka ściany WEJŚCIA — wchodzisz
    przez niego, hol jest za nim. Wiąże poprawną krawędź bbox wg strony wejścia."""
    W, H = 11.0, 8.0
    lay = _layout(W, H, side)
    assert lay.ok, f"{W}x{H} {side}: {lay.message}"
    w = _room(lay.parter_rooms, "wiatrolap")
    assert w is not None
    b = w.polygon.bounds
    on_wall = {"south": abs(b[1]) < 0.05, "north": abs(b[3] - H) < 0.05,
               "west": abs(b[0]) < 0.05, "east": abs(b[2] - W) < 0.05}[side]
    assert on_wall, f"wiatrołap nie przy ścianie wejścia {side}: bounds={b}"


# --- 3. Sąsiedztwo WC/wiatrołap ↔ hol zachowane mimo owinięcia L ---
@pytest.mark.parametrize("side", SIDES)
def test_wc_and_wiatrolap_reachable_through_hub(side):
    """F5: hol (gwiazda-rozdzielacz) dotyka WC i wiatrołapu wspólną krawędzią ≥0.9 m
    mimo owinięcia ich ramieniem L (sąsiedztwo przez którykolwiek prostokąt)."""
    W, H = 11.0, 8.0
    lay = _layout(W, H, side)
    assert lay.ok, f"{W}x{H} {side}: {lay.message}"
    hub = _room(lay.parter_rooms, "hub")
    wc = _room(lay.parter_rooms, "wc")
    w = _room(lay.parter_rooms, "wiatrolap")
    assert _shared(wc, hub) >= 0.9 - 1e-6, f"WC↔hol {_shared(wc, hub):.2f} < 0.9 [{side}]"
    assert _shared(w, hub) >= 0.9 - 1e-6, f"wiatrołap↔hol {_shared(w, hub):.2f} < 0.9 [{side}]"


# --- 4. Pełne F1: pokrycie == usable ORAZ brak nakładania (z aktywnym L) ---
def test_f1_coverage_exact_and_no_overlap_with_l_hub():
    """F1 w pełnym znaczeniu: z aktywnym L-holem suma pól == usable (==, nie <=) ORAZ
    żadne dwa pokoje się nie nakładają. Sama suma nie wykryłaby nakładania, gdyby
    opcjonalny 2. prostokąt wypadł z NoOverlap2D."""
    W, H = 11.0, 8.0
    lay = _layout(W, H, "south")
    assert lay.ok, lay.message
    # knee-wall v2 (S29): OBIE kondygnacje na pełnym obrysie (strefy niskie to
    # ograniczenie pozycji pokoi, nie powierzchni)
    usable = W * H
    for label, rooms in (("parter", lay.parter_rooms), ("pietro", lay.pietro_rooms)):
        total = sum(r.polygon.area for r in rooms)
        assert abs(total - usable) < 1e-3, f"{label}: pokrycie {total:.4f} != usable {usable}"
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ov = rooms[i].polygon.intersection(rooms[j].polygon).area
                assert ov < 1e-3, \
                    f"{label}: nakładanie {rooms[i].spec.id}∩{rooms[j].spec.id} = {ov:.4f}"


# --- 5. Hol-L jest spójnym Polygonem ---
@pytest.mark.parametrize("W,H", [(11.0, 8.0), (11.0, 9.0)])
def test_l_hub_is_connected_polygon(W, H):
    """Gdy hol jest L (unia 2 prostokątów) musi być JEDNYM spójnym Polygonem
    (ciągłość t_contig==1), nigdy rozłącznym MultiPolygonem (dwie wyspy)."""
    lay = _layout(W, H, "south")
    assert lay.ok, lay.message
    hub = _room(lay.parter_rooms, "hub")
    assert hub.polygon.geom_type == "Polygon", f"hol rozłączny: {hub.polygon.geom_type}"
    assert hub.polygon.is_valid and hub.area > 0


# --- 6. Hol nie-spine wg REALNEGO kontraktu modelu ---
@pytest.mark.parametrize("W,H", [(10.0, 8.0), (11.0, 8.0)])
def test_hub_span_within_real_model_bound(W, H):
    """F4 nie-spine wg REALNEGO modelu: bok holu ≤ max(0.6·B, 0.8·min(BW,BH)).
    (Świadomie NIE asertujemy aspect≤1.5 ani twardego 60% — w cpsat_solver.py ich nie ma,
    asercja o nich false-REDowałaby poprawny WIP.)"""
    lay = _layout(W, H, "south")
    assert lay.ok, lay.message
    hub = _room(lay.parter_rooms, "hub")
    b = hub.polygon.bounds
    span_w, span_h = b[2] - b[0], b[3] - b[1]
    max_w = max(0.6 * W, 0.8 * min(W, H))
    max_h = max(0.6 * H, 0.8 * min(W, H))
    assert span_w <= max_w + 0.05, f"hol szer {span_w:.2f} > dozwolone {max_w:.2f}"
    assert span_h <= max_h + 0.05, f"hol wys {span_h:.2f} > dozwolone {max_h:.2f}"


# --- 7. WC pozostaje prostokątem + F2 caps z aktywnym L ---
def test_wc_stays_rectangular_and_wet_rooms_capped():
    """WC NIE jest L-capable → musi zostać prostokątem (area == pole bbox). F2 niezmienione
    przez fazę 2b: lazienka ≤ 5, WC ≤ 3 na obu kondygnacjach."""
    lay = _layout(11.0, 8.0, "south")
    assert lay.ok, lay.message
    wc = _room(lay.parter_rooms, "wc")
    b = wc.polygon.bounds
    assert abs(wc.area - (b[2] - b[0]) * (b[3] - b[1])) < 0.05, "WC musi zostać prostokątem"
    caps = {"lazienka": 5.0, "wc": 3.0}
    for r in (*lay.parter_rooms, *lay.pietro_rooms):
        cap = caps.get(r.spec.id.split("_")[0])
        if cap is not None:
            assert r.area <= cap + 1e-3, f"{r.spec.id} = {r.area:.3f} > {cap}"


# --- 8. l_capable_ids falsy = no-op modelu dla mieszkań (deterministycznie) ---
def test_l_capable_none_is_model_noop_for_apartments():
    """Mieszkania M1-M5 (program_config=None, l_capable_ids falsy): ścieżka L NIE dokłada
    do modelu ŻADNYCH zmiennych ani ograniczeń. Dowodzimy DETERMINISTYCZNIE porównując
    rozmiar proto modelu (NIE wynik solvera — ten jest niedeterministyczny przy
    num_workers=8 bez random_seed, więc byte-identyczność byłaby sama w sobie flaky)."""
    from ortools.sat.python import cp_model
    from core.template_selector import load_all_templates
    from core.boundary_analyzer import analyze_boundary

    def _proto_sizes(model):
        p = model.Proto() if hasattr(model, "Proto") else model.proto
        return (len(p.variables), len(p.constraints))

    captured = []
    orig = cp_model.CpSolver.solve

    def _capture(self, model, *a, **k):
        captured.append(_proto_sizes(model))   # snapshot ZBUDOWANEGO modelu (przed solve)
        self.parameters.max_time_in_seconds = 0.01  # nie marnuj czasu — proto już mamy
        return orig(self, model, *a, **k)

    tpl = [t for t in load_all_templates() if t.typ_mieszkania == "M2"][0]
    boundary = analyze_boundary(Polygon([(0, 0), (8, 0), (8, 6), (0, 6)]), (4.0, 0))
    cp_model.CpSolver.solve = _capture
    try:
        solve_cpsat(tpl, boundary, time_limit_s=1.0)                        # legacy (bez kwarg)
        solve_cpsat(tpl, boundary, time_limit_s=1.0, l_capable_ids=None)    # jawne None
        solve_cpsat(tpl, boundary, time_limit_s=1.0, l_capable_ids=set())   # pusty set
    finally:
        cp_model.CpSolver.solve = orig

    assert len(captured) == 3, f"oczekiwano 3 solve, było {len(captured)}"
    assert captured[0] == captured[1] == captured[2], \
        f"l_capable_ids falsy ZMIENIA model (proto var/constr): {captured}"
