# Tryb architektoniczny renderera (#1-4) — design

> Data: 2026-06-18 (sesja B1-done → pivot na wiarygodność okiem). Branch `feat/sfh-open-plan-day-zone`.
> Status: zaakceptowany przez Dawida (brainstorm). Następny krok: writing-plans.

## Kontekst i premisa

B1 zamknęło wątek benchmark-score (płaskowyż room-setu, proxy-gap — patrz
[[project_proxy_gap_target_vs_realized]]). Decyzja Dawida 2026-06-18: następny lewar to
**WIARYGODNOŚĆ OKIEM**, nie cyfra benchmarku — bo score jest luźnym proxy tego, co Dawid
ocenia wzrokowo względem własnych rzutów D7 Studio (`rzuty/domy/*.pdf` = złoty standard).

RECON (świeże rendery benchmarku 2026-06-18 vs oryginały D7): **wall-poché (S31b-D1) DZIAŁA** —
grube szare mury z realną grubością, drzwi-łuki czytelne, okna w murze. Pozostałe „telle"
zdradzające „to nie prawdziwy rzut, to diagram z Pythona":

1. **Osie wykresu** — `x [m]`/`y [m]`, ticki, ramka matplotlib.
2. **Kolorowe strefy** DAY/NIGHT/SERVICE/CIRCULATION — oryginał ma białe wnętrza.
3. **Legenda kolorów** pod panelem.
4. **Schody czerwone** (`#D32F2F` straight / `#B71C1C` winder) — glif (stopnie+strzałka) OK,
   czerwień czyta się jako debug.

(Dalsze telle — okna jako pasek #5, brak tabeli/wymiarów #6, meble=bloki #7 — POZA zakresem.)

## Cel

Opcja renderera produkująca rzut „jak rysunek architektoniczny" zamiast diagramu — przez
wyłączenie 4 powyższych telli. **Tylko warstwa prezentacji (`viz/`)** — zero zmian
generatora/solvera/geometrii.

## Decyzja architektoniczna (brainstorm)

- **Flaga `architectural=False`, opt-in.** Default = kolor (dev/debug i istniejące testy
  bez zmian, ścieżka kolorowa bajt-w-bajt). Tryb czysty włączany jawnie.
- Podpięcie `architectural=True` **w tym wątku tylko w benchmarku** (`reference_benchmark.py`)
  — żeby to, co Dawid ocenia okiem, było realistyczne. MVP/AC podpinane przy ich następnym
  dotknięciu (nie rozdmuchujemy zakresu).
- Białe wnętrza z **cienką jasnoszarą krawędzią pokoju** (bezpieczna delineacja tam, gdzie
  brak muru poché) — wybór Dawida nad „czysto białe, tylko poché".

## Architektura — przepływ flagi (wszystko w `viz/`)

```
render_house_figure(…, architectural=False)        # house_preview.py — przekazuje dalej
  └─ render_two_storey(…, architectural)
       └─ _draw_storey(…, architectural)  ×2 panele (PARTER | PODDASZE)
            ├─ _draw_room(…, architectural)         # białe wnętrze + cienka szara krawędź
            └─ _draw_stair* (kolor z flagi)         # czarny zamiast czerwieni
render_floor_plan(…, architectural=False)           # parterowce + mieszkania (ta sama logika)
```

`render_rooms_only` (czysto diagnostyczny) — POZA zakresem (nie używany w benchmarku/MVP/AC).

**Potwierdzone w kodzie:** `_draw_room` jest WSPÓLNY (woła go i `_draw_storey:305`, i
`render_floor_plan:134`) — białe wnętrza (#2) wchodzą RAZ, działają w obu ścieżkach.
ALE `render_floor_plan` ma WŁASNĄ legendę (153-164), własne osie (177-178) **oraz dodatkowy
`info_text` „Outline/Rooms/Hub" (172)** = kolejny dev-tell → w trybie architektonicznym
też ukrywany. `_draw_storey` ma swoją legendę (337) i osie (345-346). Flaga musi objąć OBA
zestawy (storey + floor_plan).

## 4 zmiany (aktywne tylko gdy `architectural=True`)

| # | Zmiana | Implementacja |
|---|--------|---------------|
| 1 | **Osie OFF** | `ax.axis("off")` zamiast `set_xlabel/ylabel("x/y [m]")` (znika ramka, ticki, etykiety). `set_aspect("equal")` + `set_xlim/ylim` ZOSTAJĄ |
| 2 | **Białe wnętrza** | `_draw_room`: facecolor → biały (nie kolor strefy), edgecolor → cienka jasnoszara (np. `#BDBDBD`, lw≈0.6). Open-plan day-zone: bez wypełnienia, cienki obrys unii zostaje (salon+kuchnia scalają się wizualnie = poprawnie). Strefy knee-wall (skos) ZOSTAJĄ (przyciemnienie + przerywana linia ścianki — architektoniczne) |
| 3 | **Bez legendy** | pomiń wywołania `ax.legend(...)` (w `_draw_storey` i `render_floor_plan`) |
| 4 | **Schody czarne** | `#D32F2F`/`#B71C1C` → czarny (np. `#212121`) w `_draw_stair`/`_draw_stair_in_room`/`_draw_winder_in_room`. Glif (stopnie + strzałka kierunku) strukturalnie BEZ zmian — tylko kolor |

Co ZOSTAJE w obu trybach: poché ścian, drzwi-łuki, okna (paski na fasadzie), etykiety pokoi
z OA, obrys, tytuły paneli PARTER/PODDASZE, aspect/limity.

## Testy (TDD)

1. **`tests/test_architectural_mode.py`** (nowy, RED-first):
   - render z `architectural=True` → `ax.get_legend() is None`;
   - osie wyłączone (`ax.axison is False` lub brak xlabel/widocznej ramki);
   - patche pokoi mają białe wypełnienie (nie kolor strefy) — sprawdzić facecolor reprez. pokoju;
   - smoke: nie rzuca, zapis PNG działa.
2. **Regresja:** default (`architectural=False`) — istniejące testy renderera zielone
   (ścieżka kolorowa nietknięta). Jeśli brak dedykowanych testów renderera default — dodać
   minimalny smoke „default ma legendę + osie" jako regression-lock.

## Walidacja wizualna (po implementacji)

Wygenerować 1-2 rendery domów z `architectural=True` (CPU wolne) i porównać OKIEM z
oryginałami D7 (`rzuty/domy/`): czy znikły 4 telle, czy poché/drzwi/etykiety czytelne,
czy białe wnętrza + szara krawędź nie gubią pokoi. Przegląd z Dawidem.

## Zakres plików

- `viz/plan_renderer.py` — flaga + 4 zmiany (osie, `_draw_room`, legendy, schody).
- `viz/house_preview.py` — przekazanie flagi przez `render_house_figure`.
- `notebooks/reference_benchmark.py` — `architectural=True` w `score_project`.
- `tests/test_architectural_mode.py` — nowy.
- BEZ zmian: core/, solver, geometria, ścieżka kolorowa (default).

## Poza zakresem (YAGNI — osobne wątki)

- Okna jako symbol 3-liniowy w murze (#5).
- Tabela zestawienia powierzchni + łańcuchy wymiarowe + osie konstrukcyjne + strzałka N (#6).
- Realistyczne symbole mebli CAD (#7).
- Podpięcie `architectural=True` w MVP/AC (przy ich następnym dotknięciu).
- `render_rooms_only` (diagnostyczny).
