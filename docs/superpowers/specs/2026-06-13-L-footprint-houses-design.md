# Spec: L-kształtne footprinty dla domów 2-kondygnacyjnych (notch-aware rdzeń klatki)

> Data: 2026-06-13 · Branch: `feat/sfh-open-plan-day-zone` · Stage 4 (FloorPlan6)
> Decyzje Dawida (2026-06-13): zacząć od L (różnoboczne osobnym etapem później);
> klatka na **wewnętrznym narożniku** → ZREWIDOWANE na **róg diagonalnie przeciwny do
> notcha** (wewnętrzny narożnik = INFEASIBLE, sonda; sekcja Geometria); zakres v1 = **tylko rdzeń
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
- `_reserve_core` świadomy notcha → rdzeń w litej GŁÓWNEJ BRYLE L, zakotwiony w
  **rogu bbox diagonalnie przeciwnym** do wcięcia (zob. sekcja Geometria — rewizja).
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

**Geometria — róg DIAGONALNIE PRZECIWNY do notcha.** ⚠️ REWIZJA 2026-06-13 (sonda
`notebooks/lcore_placement_probe.py`): pierwotny wybór „wewnętrzny narożnik" okazał
się **geometrycznie INFEASIBLE** — wklęsły wierzchołek to gardło cyrkulacji między
skrzydłami; przypięta tam klatka + notch (dwie przeszkdy) zatykają jedyne przejście
→ solver nie ułoży 8-pokojowego programu parteru. Zmierzone (L 102 m²): narożnik
flush = INFEASIBLE 0.6 s, narożnik pionowy = INFEASIBLE 2.5 s, narożnik +offset 0.5 m
= INFEASIBLE 3.0 s, **róg przeciwny = OPTIMAL 11.5 s**. Decyzja Dawida 2026-06-13:
przejść na róg przeciwny.

Notch zajmuje jeden róg bbox (pojedyncze wcięcie L). Rdzeń kotwiczony w rogu bbox
**diagonalnie przeciwnym** — zawsze lity, z dala od zgięcia:

| Notch dotyka | Rdzeń kotwiczony |
|---|---|
| lewej + dolnej (dolny-lewy) | prawy-górny `(W−sw, H−sh)` |
| prawej + dolnej (dolny-prawy) | lewy-górny `(0, H−sh)` |
| lewej + górnej (górny-lewy) | prawy-dolny `(W−sw, 0)` |
| prawej + górnej (górny-prawy) | lewy-dolny `(0, 0)` |

Formuła: `on_left = notch.x < eps`, `on_bottom = notch.y < eps`;
`cx = (W−sw) if on_left else 0.0`; `cy = (H−sh) if on_bottom else 0.0`. Wymiary
`sw, sh` z `_stair_core_dims` bez zmian (bieg prosty wzdłuż kalenicy). Centralność
zapewnia hol L-capable owijający zgięcie; schody siedzą w bryle skrzydła — jak
realne L-domy (korpus: schody przy holu, w bryle, nie w samym zgięciu).

**Fallback / degeneracja.** Róg przeciwny jest zawsze lity dla pojedynczego notcha,
więc rdzeń nie nachodzi na wcięcie z definicji. Gdy lita bryła < program parteru
(notch za duży) → solver zwróci `ok=False` z czytelnym komunikatem (jak dziś dla za
małych obrysów) — bez śmieciowego układu.

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
3. **`test_core_anchored_opposite_notch`** — rdzeń przy rogu bbox diagonalnie
   przeciwnym do notcha (lewy-górny dla notcha dolny-prawy itd.), ≥2 położenia.
4. **`test_stairs_vertically_aligned_on_L`** — `schody` parteru i poddasza mają ten
   sam bbox (piony).
5. **`test_single_storey_L_still_ok`** — parterowiec L generuje 4-syp (regression-lock).
6. **`test_reserve_core_rectangle_unchanged`** — notch=None → `_reserve_core` zwraca
   identyczną krotkę jak przed zmianą (kilka bbox×wejście).

Weryfikacja: testy + render kontrolny L 2-kond. (`viz/house_preview`) — obejrzeć
piony, hol na zgięciu, garaż w skrzydle.

## Ryzyka

- **Róg przeciwny vs strona wejścia** mogą się „bić" (wejście blisko rogu rdzenia).
  v1: rdzeń bezwarunkowo w rogu przeciwnym do notcha; hol L-capable nadrabia routing
  (zweryfikowane: entry=north + rdzeń lewy-górny = OPTIMAL). Entry-aware wybór rogu
  (gdy >1 lity róg pasuje) = ewentualny refinement, gdy któraś strona wejścia padnie.
- **Poddasze dużych L** może zostać UNKNOWN (poza zakresem) — wtedy `ok=False`,
  uczciwy komunikat, nie udajemy sukcesu; kolejkujemy room-count poddasza.
