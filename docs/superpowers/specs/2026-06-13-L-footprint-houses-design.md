# Spec: L-kształtne footprinty dla domów 2-kondygnacyjnych (notch-aware rdzeń klatki)

> Data: 2026-06-13 · Branch: `feat/sfh-open-plan-day-zone` · Stage 4 (FloorPlan6)
> Decyzje Dawida (2026-06-13): zacząć od L (różnoboczne osobnym etapem później);
> klatka na **wewnętrznym narożniku skrzydeł**; zakres v1 = **tylko rdzeń
> notch-aware** (poddasze dużych L jako osobny krok).

## Problem

Domy **2-kondygnacyjne** na obrysie L-kształtnym są INFEASIBLE. Bloker namierzony
co do linijki: `core/house_layout._reserve_core` liczy pozycję rdzenia klatki na
`boundary.bbox` (pełny prostokąt) i **ignoruje notch**. Dla L rdzeń może wylądować
w wcięciu (które solver trzyma jako przeszkodę NoOverlap2D), a ponieważ pokój
`schody` jest **przypięty** do rdzenia 4 równościami (gwarancja pionów parter↔
poddasze), pin w przeszkodzie → INFEASIBLE na obu kondygnacjach.

**Dowód (sonda 2026-06-13, L 12×10 − notch 4.5×4 = 102 m²):**
- parterowiec L: **OK** (12 pokoi, 4-syp, notch respektowany) — solver radzi sobie
  z L bez rdzenia,
- 2-kond. L: **parter=UNKNOWN, pietro=UNKNOWN** — bloker rdzenia.

Korpus (ekstrakcja S30, `reference_plans_full.json`): **wszystkie duże domy
≥110 m² są L/T** (pt 166 L, ar02-1b 121 L, a2-2 111 L) — L to nie dodatek, to
warunek wiarygodności dla domów garażowych.

## Zakres

**W zakresie (v1):**
- `_reserve_core` świadomy notcha → rdzeń w litej części L, zakotwiony przy
  **wewnętrznym (wklęsłym) narożniku** skrzydeł.
- Wszystkie 4 położenia notcha (każdy róg bbox) × strony wejścia.
- Test regresji parterowca L (już działa — zablokować).
- Gwarancja braku regresji: notch=None → `_reserve_core` bajt-w-bajt jak dziś.

**Poza zakresem (osobne kroki):**
- Poddasze dużych L (≥120 m² → eff ~104 → 9 pokoi z garderobą = osobna krawędź
  room-count; może zostać loterią po tej naprawie — mierzymy, potem decydujemy).
- Różnoboczne / dowolne wielokąty (>1 notch, skosy, T) — osobny etap (decyzja Dawida).
- Mieszkania M1-M5 (L/U/trapez już działają — nietknięte).

## Projekt

### Komponent: notch-aware `_reserve_core(bbox, entry_point, notch=None, force_straight)`

Jedna funkcja, jedno zadanie: zwrócić `(cx, cy, sw, sh)` rdzenia (bbox-relative).
Sygnatura rozszerzona o `notch: Optional[NotchInfo] = None`. Wymiary rdzenia
(`sw, sh` z `_stair_core_dims`, bieg prosty wzdłuż kalenicy) **bez zmian** — zmienia
się tylko **pozycja** gdy notch jest obecny.

**Geometria wklęsłego narożnika.** Notch to prostokąt `(nx, ny, nw, nh)` wycięty z
rogu bbox `(0,0,W,H)`. Wklęsły wierzchołek L = róg notcha leżący WEWNĄTRZ bbox
(nie na krawędzi). Lita część przylegająca do niego = kwadrant po przekątnej od
notcha. Formuła per położenie notcha (który róg bbox zajmuje):

| Notch w rogu | Wklęsły wierzchołek | Rdzeń kotwiczony (lita strona) |
|---|---|---|
| dolny-lewy `(0,0)` | `(nw, nh)` | x ≥ nw przy dole **lub** y ≥ nh przy lewej |
| dolny-prawy `(W−nw,0)` | `(W−nw, nh)` | x+sw ≤ W−nw przy dole **lub** y ≥ nh przy prawej |
| górny-lewy `(0,H−nh)` | `(nw, H−nh)` | analogicznie |
| górny-prawy `(W−nw,H−nh)` | `(W−nw, H−nh)` | analogicznie |

Rdzeń sadzimy tak, by jeden jego **róg dotykał wklęsłego wierzchołka** od litej
strony, a orientacja biegu szła wzdłuż dłuższej osi litej bryły (kalenica). Hol
(L-capable, mechanika S26/27) zajmie zgięcie i sięgnie obu skrzydeł.

**Fallback (skrzydło za wąskie).** Jeśli rdzeń `sw×sh` nie mieści się w litym pasie
przy narożniku (wąskie skrzydło), dosnap rdzeń do najbliższej krawędzi litej części
(analogia `ATTIC_CORE_SNAP=1.5`, S27) — byle CAŁY rdzeń był poza notchem. Gdy nawet
to nie daje rady (degeneracja) → zostaw przy zewnętrznej ścianie litej bryły
(stara logika ograniczona do solid-bbox); generate_house i tak zwróci `ok=False`
z czytelnym komunikatem zamiast śmieciowego układu.

### Integracja w `generate_house`

`generate_house` (2-kond.) woła `_reserve_core(boundary.bbox, entry_point,
notch=boundary.notch, force_straight=True)`. `analyze_boundary` już wykrywa notch
(`_detect_notch`), więc `boundary.notch` jest dostępny. Rdzeń trafia do OBU solve'ów
(parter + pietro) jak dziś → te same piony. Reszta ścieżki (room-set netto/brutto,
sąsiedztwa korpusowe, knee-wall low strips, L-capable hol) bez zmian — solver już
trzyma notch jako przeszkodę dla pozostałych pokoi.

`attic_low_strips` liczy pasy na bbox — pasy mogą sięgać notcha (nieszkodliwe: brak
pokoju w notchu). Bez zmian w v1.

### Dane / przepływ

Bez nowych struktur. `NotchInfo(x,y,width,height)` już istnieje. Przepływ:
`polygon (L) → analyze_boundary → boundary.notch → _reserve_core(notch=…) →
core w litej części → solve_cpsat(reserved_core=core) ×2 → TwoStoreyLayout`.

### Obsługa błędów

- notch=None → ścieżka identyczna z dzisiejszą (regression-guard test).
- rdzeń nie mieści się nawet po snapie → `ok=False` + komunikat (nie śmieciowy układ).
- notch tak duży, że lita część < program parteru → `ok=False` (jak dziś dla za
  małych obrysów).

## Testowanie (RED-first)

Nowy `tests/test_house_lfootprint.py`:
1. **`test_l_2storey_generates`** — L 102 m² 2-kond. → `lay.ok` (dziś UNKNOWN). RED.
2. **`test_core_not_in_notch`** — rdzeń (`stair_core`) nie przecina notcha (geom).
3. **`test_core_at_inner_corner`** — róg rdzenia styka się z wklęsłym wierzchołkiem
   (tolerancja snap), dla ≥2 położeń notcha.
4. **`test_stairs_vertically_aligned_on_L`** — `schody` parteru i poddasza mają ten
   sam bbox (piony).
5. **`test_single_storey_L_still_ok`** — parterowiec L generuje 4-syp (regression-lock).
6. **`test_reserve_core_rectangle_unchanged`** — notch=None → `_reserve_core` zwraca
   identyczną krotkę jak przed zmianą (kilka bbox×wejście).

Weryfikacja: testy + render kontrolny L 2-kond. (`viz/house_preview`) — obejrzeć
piony, hol na zgięciu, garaż w skrzydle.

## Ryzyka

- **Wklęsły narożnik vs strona wejścia** mogą się „bić" (wejście na skrzydle
  przeciwnym do narożnika) → rdzeń daleko od wejścia. Mitigacja: orientacja biegu z
  litej osi, hol L-capable nadrabia dystans (jak na wąskich mieszkaniach S26).
- **Poddasze dużych L** może zostać UNKNOWN (poza zakresem) — wtedy `ok=False`,
  uczciwy komunikat, nie udajemy sukcesu; kolejkujemy room-count poddasza.
