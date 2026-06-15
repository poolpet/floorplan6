# Dzień 2 — Schody zabiegowe (winder) domyślne — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Domy 2-kondygnacyjne na obrysach compact (aspect ≤ 1.4 — modalny przypadek) mają domyślnie schody **zabiegowe/dwubiegowe (U)** zamiast pojedynczego biegu prostego; renderer rysuje glif winder zamiast prostego biegu.

**Architecture:** Dwie zmiany. (1) **Logika+model:** zdjąć `force_straight=True` w `generate_house` (1 miejsce) — `_stair_core_dims` już zwraca `kind` "u"/"straight" wg proporcji; przepchnąć `kind` (dziś wyrzucany) na `TwoStoreyLayout.stair_kind` i na pokój `schody`. (2) **Renderer:** `_draw_stair_in_room` rozgałęzia na `kind` — dla "u" rysuje glif dwubiegowy (dwa biegi + spocznik + strzałka), inaczej obecny bieg prosty.

**Tech Stack:** Python 3.10+, Shapely, matplotlib, pytest, OR-Tools CP-SAT (solver — nie ruszamy).

**Dowód wykonalności (probe `notebooks/winder_stair_probe.py`, uruchomiony):**
```
[11x8 (88)   straight] parter=UNKNOWN  poddasze=OPTIMAL
[11x8 (88)   u 2.4x2.4] parter=FEASIBLE poddasze=FEASIBLE   ← U lepszy
[13x10 (130) straight] parter=UNKNOWN  poddasze=FEASIBLE
[13x10 (130) u 2.4x2.4] parter=FEASIBLE poddasze=FEASIBLE   ← U lepszy
```
Powód `force_straight` (S26: U-rdzeń zostawiał martwą kieszeń w wąskim paśmie poddasza) jest **obsolete** — knee-wall v2 dało poddaszu pełny footprint, a schody są zwolnione ze strefy niskiej ścianki (`house_layout.py:412`). Obrysy aspect > 1.4 i tak dostają bieg prosty (`_stair_core_dims:108`) — to zostaje.

---

## File Structure
- `core/house_layout.py` — drop force_straight (:386), compute+store `stair_kind`; `TwoStoreyLayout` +pole; set na `schody`.
- `core/models.py` — `Room` +pole `stair_kind`.
- `viz/plan_renderer.py` — glif winder (`_draw_winder_in_room`) + rozgałęzienie w `_draw_stair_in_room`.
- `tests/test_house_staircase.py`, `tests/test_house_staircase_b.py` — aktualizacja 2 expected + nowe testy kind.

**Poza zakresem dziś:** guard kolizji labeli (latentny — `_label_anchor` repeluje tylko od własnych mebli; nie widoczne na bieżących renderach; raportowane Dawidowi, do osobnego taska); smoke AC (wymaga AC otwartego u Dawida); fallback `_draw_stair` (degenerat smoke bez pokoju 'schody') zostaje prosty.

---

## Task 1: Winder default + plumb `stair_kind` (logika+model, TDD)

**Files:** Modify `core/house_layout.py`, `core/models.py`, `tests/test_house_staircase.py`, `tests/test_house_staircase_b.py`.

- [ ] **Step 1: Failing testy.** Dopisz w `tests/test_house_staircase_b.py` (ma helpery `_gen`, `_room`):

```python
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
```

- [ ] **Step 2: Uruchom — FAIL** (AttributeError: 'TwoStoreyLayout' object has no attribute 'stair_kind'):
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_staircase_b.py::test_compact_house_gets_winder_u_kind -v`

- [ ] **Step 3: `Room` +pole `stair_kind`.** W `core/models.py`, dataclass `Room` (~linia 200-208), po `proportion: float = 1.0` dodaj:
```python
    proportion: float = 1.0
    stair_kind: Optional[str] = None   # 'u'/'straight' tylko dla pokoju 'schody'; inaczej None
```
(`Optional` jest już zaimportowany w models.py.)

- [ ] **Step 4: `TwoStoreyLayout` +pole.** W `core/house_layout.py` (~linia 134), po `stair_core: tuple[...] = (...)` dodaj:
```python
    stair_kind: str = "straight"   # 'u' (zabiegowe) / 'straight' — wg proporcji obrysu
```

- [ ] **Step 5: Zdejmij force_straight + policz kind w `generate_house`.** Znajdź (~linie 384-387):
```python
    # Knee-wall (S26): bieg prosty wzdłuż kalenicy — patrz _stair_core_dims(force_straight).
    # S30: notch-aware — dla L rdzeń ląduje przy wklęsłym narożniku, nie w wcięciu.
    core = _reserve_core(boundary.bbox, entry_point, force_straight=True,
                         notch=boundary.notch)
```
Zamień na:
```python
    # Winder default (S31b): force_straight ZDJĘTY. Po knee-wall v2 poddasze ma pełny
    # footprint i schody są zwolnione ze strefy niskiej ścianki, więc U-rdzeń jest
    # wykonalny (probe: parter FEASIBLE vs straight UNKNOWN na 88/130 m²). Obrysy aspect
    # > STAIR_ASPECT_THRESHOLD i tak dostają bieg prosty. S30: notch-aware (róg przeciwny wcięciu).
    core = _reserve_core(boundary.bbox, entry_point, notch=boundary.notch)
    _bw = boundary.bbox[2] - boundary.bbox[0]
    _bh = boundary.bbox[3] - boundary.bbox[1]
    _csw, _csh, stair_kind = _stair_core_dims(_bw, _bh)
```

- [ ] **Step 6: Wstrzyknij `stair_kind` do wyniku + na pokoje 'schody'.** Znajdź końcówkę `generate_house` (~linie 444-449):
```python
    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core, boundary=boundary, attic_low_strips=strips)
    return TwoStoreyLayout(ok=True, parter_rooms=r_parter.rooms, pietro_rooms=r_pietro.rooms,
                           stair_core=core, boundary=boundary, attic_low_strips=strips)
```
Zamień na:
```python
    if r_parter.status not in ("OPTIMAL", "FEASIBLE") or r_pietro.status not in ("OPTIMAL", "FEASIBLE"):
        return TwoStoreyLayout(ok=False,
            message=f"Solver nie znalazl ukladu (parter={r_parter.status}, pietro={r_pietro.status}).",
            stair_core=core, stair_kind=stair_kind, boundary=boundary, attic_low_strips=strips)
    for _rooms in (r_parter.rooms, r_pietro.rooms):
        for _r in _rooms:
            if _r.spec.id == "schody":
                _r.stair_kind = stair_kind
    return TwoStoreyLayout(ok=True, parter_rooms=r_parter.rooms, pietro_rooms=r_pietro.rooms,
                           stair_core=core, stair_kind=stair_kind, boundary=boundary,
                           attic_low_strips=strips)
```

- [ ] **Step 7: Zaktualizuj 2 istniejące expected (były liczone z force_straight=True).**
  W `tests/test_house_staircase.py` linia 79, zmień:
  ```python
      sw, sh, _ = _stair_core_dims(10.0, 8.0, force_straight=True)
  ```
  na:
  ```python
      sw, sh, _ = _stair_core_dims(10.0, 8.0)   # winder default (S31b): 10×8 aspect 1.25 → U
  ```
  W `tests/test_house_staircase_b.py` linia 40, zmień:
  ```python
      # dom 2-kond. = bieg prosty wzdłuż kalenicy (knee-wall, patrz _stair_core_dims)
      sw, sh, _ = _stair_core_dims(10.0, 8.0, force_straight=True)
  ```
  na:
  ```python
      # winder default (S31b): 10×8 (aspect 1.25 ≤ 1.4) → rdzeń U; band 4–6 m² nadal trzyma (5.76)
      sw, sh, _ = _stair_core_dims(10.0, 8.0)
  ```

- [ ] **Step 8: Uruchom testy schodów — PASS.**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_staircase.py tests/test_house_staircase_b.py -v`
Oczekiwane: zielone (2 nowe + zaktualizowane). ⚠️ JEŚLI `test_generate_house_feasible_and_schody_separate_from_hol` (test_house_staircase.py) flakuje na `assert layout.ok` przez UNKNOWN @45 s (U-rdzeń przesuwa perf parteru 10×8) — to NIE słabnięcie asercji, tylko realna granica perf: podnieś w TYM teście `time_limit_s=45.0` → `60.0` (sibling test_house_staircase_b już używa 60 s). Najpierw uruchom 2-3× by potwierdzić, że to czas, nie błąd logiczny. Inne flaki CPU (memory: 11×11, batch) weryfikuj w izolacji.

- [ ] **Step 9: Commit.**
```bash
git add core/house_layout.py core/models.py tests/test_house_staircase.py tests/test_house_staircase_b.py
git commit -m "feat(stage4): schody zabiegowe (U) domyślne dla obrysów compact + plumb stair_kind

Zdjęty force_straight (obsolete po knee-wall v2; probe: U parter FEASIBLE vs straight
UNKNOWN). stair_kind przepchnięty na TwoStoreyLayout + pokój 'schody' dla renderera.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Glif schodów zabiegowych w rendererze (wizualne)

Renderer rozgałęzia na `schody.stair_kind`: "u" → glif dwubiegowy (dwa biegi + spocznik pełnej szerokości + strzałka „w górę"), inaczej obecny bieg prosty. `stair_run_orientation` (oś + zwrot od holu) ZOSTAJE — testy od niej zależą; glif tylko z niej korzysta. Weryfikacja: render-test zielony + bramka wizualna (test geometryczny glifu jest niepraktyczny — to rysunek).

**Files:** Modify `viz/plan_renderer.py`.

- [ ] **Step 1: Dodaj `_draw_winder_in_room` tuż przed `_draw_stair_in_room` (~linia 306).**
```python
def _draw_winder_in_room(ax, schody, hol):
    """Glif schodów dwubiegowych/zabiegowych (U): dwa biegi rozdzielone studnią +
    spocznik pełnej szerokości na końcu OD holu + strzałka 'w górę' jednym biegiem.
    Orientacja z stair_run_orientation (oś biegu + zwrot odchodzący od holu)."""
    sx, sy, ex, ey = schody.polygon.bounds
    sw, sh = ex - sx, ey - sy
    color = "#B71C1C"
    hb = hol.polygon.bounds if (hol is not None and getattr(hol, "polygon", None) is not None) else None
    axis, arrow = stair_run_orientation(schody.polygon.bounds, hb)
    LAND = 0.30                                   # udział spocznika w głębokości biegu
    if axis == "vertical":                        # biegi pionowe, studnia pionowa w X
        xm = sx + sw / 2.0
        ax.plot([xm, xm], [sy, ey], color=color, lw=1.0, zorder=5)
        far_top = (arrow == "N")                  # 'w górę' = N → spocznik u góry
        ly0, ly1 = (ey - sh * LAND, ey) if far_top else (sy, sy + sh * LAND)
        ax.add_patch(mpatches.Rectangle((sx, ly0), sw, ly1 - ly0, facecolor="none",
                                        edgecolor=color, lw=0.8, zorder=5))
        rlo, rhi = (sy, ly0) if far_top else (ly1, ey)
        n = max(2, int((rhi - rlo) / 0.28))
        for k in range(1, n):
            y = rlo + (rhi - rlo) * k / n
            ax.plot([sx, xm], [y, y], color=color, lw=0.5, zorder=5)
            ax.plot([xm, ex], [y, y], color=color, lw=0.5, zorder=5)
        xL = sx + sw * 0.25
        a0, a1 = (rlo + (rhi - rlo) * 0.1, rhi) if far_top else (rhi - (rhi - rlo) * 0.1, rlo)
        ax.annotate("", xy=(xL, a1), xytext=(xL, a0),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.2), zorder=6)
    else:                                         # biegi poziome, studnia pozioma w Y
        ym = sy + sh / 2.0
        ax.plot([sx, ex], [ym, ym], color=color, lw=1.0, zorder=5)
        far_right = (arrow == "E")
        lx0, lx1 = (ex - sw * LAND, ex) if far_right else (sx, sx + sw * LAND)
        ax.add_patch(mpatches.Rectangle((lx0, sy), lx1 - lx0, sh, facecolor="none",
                                        edgecolor=color, lw=0.8, zorder=5))
        rlo, rhi = (sx, lx0) if far_right else (lx1, ex)
        n = max(2, int((rhi - rlo) / 0.28))
        for k in range(1, n):
            x = rlo + (rhi - rlo) * k / n
            ax.plot([x, x], [sy, ym], color=color, lw=0.5, zorder=5)
            ax.plot([x, x], [ym, ey], color=color, lw=0.5, zorder=5)
        yL = sy + sh * 0.25
        a0, a1 = (rlo + (rhi - rlo) * 0.1, rhi) if far_right else (rhi - (rhi - rlo) * 0.1, rlo)
        ax.annotate("", xy=(a1, yL), xytext=(a0, yL),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.2), zorder=6)
```

- [ ] **Step 2: Rozgałęź `_draw_stair_in_room` na kind (początek funkcji, ~linia 306-313).** Znajdź nagłówek + pierwsze linie:
```python
def _draw_stair_in_room(ax, schody, hol):
    """Symbol biegu WEWNĄTRZ pokoju 'schody' — stopnie + strzałka 'w górę' (bez
    osobnego prostokąta/etykiety; pokój jest już narysowany i podpisany 'Schody')."""
    sx, sy, ex, ey = schody.polygon.bounds
```
Wstaw rozgałęzienie zaraz po docstringu:
```python
def _draw_stair_in_room(ax, schody, hol):
    """Symbol biegu WEWNĄTRZ pokoju 'schody' — stopnie + strzałka 'w górę' (bez
    osobnego prostokąta/etykiety; pokój jest już narysowany i podpisany 'Schody').
    Dla stair_kind=='u' rysuje glif dwubiegowy (zabiegowe), inaczej bieg prosty."""
    if getattr(schody, "stair_kind", None) == "u":
        _draw_winder_in_room(ax, schody, hol)
        return
    sx, sy, ex, ey = schody.polygon.bounds
```

- [ ] **Step 3: Render-test — PASS (glif nie wywraca renderu 2-kond.).** Po Tasku 1 `generate_house` zwraca domyślnie U-rdzeń, więc `test_two_storey_render` ćwiczy ścieżkę winder:
`PYTHONPATH=. venv/bin/python -m pytest tests/test_two_storey_render.py tests/test_house_staircase_b.py::test_stair_run_orientation_points_away_from_hol -v`
Oczekiwane: zielone.

- [ ] **Step 4: Commit.**
```bash
git add viz/plan_renderer.py
git commit -m "feat(viz): glif schodów zabiegowych (U) — dwa biegi + spocznik + strzałka

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Bramka końcowa Dnia 2
- [ ] **Step A: Sweep regresji.**
`PYTHONPATH=. venv/bin/python -m pytest tests/test_house_staircase.py tests/test_house_staircase_b.py tests/test_two_storey_render.py tests/test_furniture.py tests/test_wall_poche.py -q`
Oczekiwane: zielone (flaki perf weryfikuj w izolacji per memory).

- [ ] **Step B: Bramka wizualna.** `PYTHONPATH=. venv/bin/python notebooks/sfh_furnished_smoke.py` → otwórz `notebooks/output/sfh_furnished.png`. Sprawdź: schody na OBU kondygnacjach rysują się jako **dwubiegowe (U) ze spocznikiem**, nie pojedynczy prosty bieg ze strzałką przez całość; orientacja sensowna (wejście od strony holu). Jeśli glif nieczytelny (biegi/strzałka/spocznik mylące) — dostrój `LAND`, liczbę stopni, pozycję strzałki (to iteracja wizualna; render-test chroni przed crashem).

- [ ] **Step C: Checkpoint z Dawidem** (przed/po schodów) + przypomnij: smoke AC czeka na AC otwarte; guard kolizji labeli zaraportowany jako latentny (osobny task).

---

## Self-Review (autor)
- **Pokrycie:** winder default → Task 1 (drop force_straight + kind plumb); glif → Task 2. Higiena labeli i smoke AC świadomie poza zakresem (latentne/wymaga Dawida) — zaraportowane.
- **Placeholdery:** brak — pełny kod i komendy.
- **Spójność typów:** `stair_kind` jako str "u"/"straight" — `_stair_core_dims` zwraca "u"/"straight" (models test_square_outline_gives_u_stair potwierdza "u"); `TwoStoreyLayout.stair_kind` i `Room.stair_kind` tego samego typu; renderer czyta `getattr(schody, "stair_kind", None) == "u"`. `stair_run_orientation` nietknięty (kontrakt testów zachowany).
- **Ryzyko:** 10×8 U @45 s perf-flake — mitygacja w Step 8 (bump do 60 s po potwierdzeniu, nie słabnięcie asercji). Większy U-rdzeń (5.76 vs 4.62) — band 4–6 m² i hol-compact nadal trzymają; probe pokazał U lepszy dla parteru.
