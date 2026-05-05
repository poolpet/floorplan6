# TEMPLATES_GUIDE — 3 zestawy szablonów

> **Kontekst:** w toku pracy nad poprzednimi wersjami powstały TRZY różne zestawy "szablonów". Każdy ma inne przeznaczenie. Mylenie ich = bugi i marnowany czas.

---

## SKĄD TE TRZY ZESTAWY

W FloorPlan2 i wczesnym FloorPlan4 było tylko 1 zestaw — ręcznie napisane reguły. Z czasem powstały dodatkowo:
- **Zestaw 2** — żeby trenować/walidować solver na rzeczywistych mieszkaniach
- **Zestaw 3** — z grafem sąsiedztwa wypełnionym (do template_selectora który próbuje znaleźć podobny rzut do obrysu użytkownika)

W FloorPlan4_CPP skopiowano tylko Zestaw 1 (constraints). FloorPlan6 ma wszystkie trzy.

---

## ZESTAW 1: CONSTRAINT TEMPLATES (`templates/`) — 7 plików

**Lokalizacja:** `FloorPlan6/templates/M*.json`

**Schema:**
```json
{
  "id": "M3_standard",
  "nazwa": "3-pokojowe standardowe",
  "typ_mieszkania": "M3",
  "pokoje": [
    {
      "id": "hub",
      "nazwa": "Przedpokój",
      "strefa": "KOMUNIKACJA",
      "wymaga_okna": false,
      "priorytet_fasady": null,
      "min_powierzchnia": 5.0,
      "opt_powierzchnia": 8.1,
      "min_szerokosc": 1.2,
      "max_proporcja": 2.0,
      "procent_powierzchni": [0.08, 0.15]
    },
    ...
  ],
  "sasiedztwo": [
    {"room_a": "hub", "room_b": "_outside", "connection_type": "entry_door"},
    {"room_a": "hub", "room_b": "lazienka", "connection_type": "door"},
    ...
  ]
}
```

**Co zawiera:** REGUŁY (constraints) — co MA BYĆ w mieszkaniu danego typu. **Bez geometrii.**

**Pola pokoju:**
- `min_powierzchnia` / `opt_powierzchnia` (m²)
- `min_szerokosc` (m)
- `max_proporcja` (aspect ratio)
- `procent_powierzchni` [min%, max%] względem usable area
- `wymaga_okna` (bool)
- `priorytet_fasady` (int, niższy = wyższy priorytet)
- `preferowana_orientacja` (lista: "S", "SW", "SE", …)

**Pola sąsiedztwa:**
- `room_a`, `room_b` (id pokoju lub `"_outside"`)
- `connection_type`: `"entry_door"` / `"door"` / `"opening"`

**Pliki (7):**
| Plik | Typ | Pokoje | Notes |
|------|-----|--------|-------|
| M1_standard.json | M1 | 4 (hub, łazienka, sypialnia, salon_aneks) | min |
| M2_standard.json | M2 | 4 (hub, łazienka, sypialnia, salon_aneks) | |
| M3_standard.json | M3 | 5 (+ sypialnia_2) | |
| M3_wc.json | M3 | 6 (+ wc) | dla obrysu z miejscem na osobny WC |
| M4_standard.json | M4 | 6 | |
| M4_2laz.json | M4 | 7 (+ 2-ga łazienka) | dwa łazienki tylko w M4+ (F8) |
| M5_standard.json | M5 | 7-8 | max |

**Po co:**
- `core/cpsat_solver.py` używa tych constraint templates do generowania nowych rozkładów
- `core/template_selector.py` wybiera kandydatów na podstawie typu mieszkania i rozmiaru obrysu
- `core/validator.py` sprawdza czy wynik solvera spełnia constraints

**Kiedy użyć:** **ZAWSZE w pipeline generowania**.

---

## ZESTAW 2: TRACED REAL APARTMENTS — bez wypełnionego grafu

> **Status w FloorPlan6:** NIESKOPIOWANE (były w FP4 `rzuty/templates/`, 41 plików, edges to placeholdery `-1`).
>
> **Lokalizacja źródłowa:** `FloorPlan4/rzuty/templates/PL_*.json` (41 plików).
> **W FP6:** folder `rzuty/` pusty — możemy zaimportować w przyszłości jeśli potrzebne.

**Schema:** podobny do Zestawu 3, ALE pole `edges[].room_a_idx` i `room_b_idx` to wszystkie `-1` (placeholder).

**Co zawiera:** geometria pokoi (polygons), facades, stretch — ALE BEZ grafu sąsiedztwa (graph szkielet jest, dane nie).

**Po co:** miały być reference dataset, ale ktoś nie skończył wypełniać edges. **Niedokończona praca.** 14 z nich nie ma odpowiednika w Zestawie 3.

**Kiedy użyć:** rzadko. Tylko jeśli potrzebujesz GEOMETRII pokoju którego nie ma w Zestawie 3 (14 takich: PL_NL_16, D14, D24, E11, F34, F40, G53, J25, J27, J41, K40, PL_TVR_17, 21, 23). Wtedy importuj z FP4 ad-hoc.

---

## ZESTAW 3: TRACED REAL APARTMENTS — Z WYPEŁNIONYM GRAFEM ⭐ (`data/plans/`)

**Lokalizacja:** `FloorPlan6/data/plans/PL_*.json` — 27 plików.

**Schema:**
```json
{
  "id": "PL_NL_29",
  "original_id": "NL_29",
  "copies": ["NL_08", "NL_13", "NL_16"],
  "total_area_m2": 67.08,
  "width_m": 13.97,
  "height_m": 7.44,
  "aspect_ratio": 1.878,
  "apartment_type": "M3",
  "n_rooms": 5,
  "rooms": [
    {
      "room_type": 5,
      "label": "HOL",
      "polygon": [{"x": 9.528, "y": 1.815}, ...],
      "area_m2": 8.49,
      "facades": [false, false, false, false, false, false],
      "stretch": ["ADAPT", "ADAPT", ...]
    },
    ...
  ],
  "edges": [
    {"room_a_idx": 0, "room_b_idx": -1, "edge_type": "entry_door"},  ← hub → outside
    {"room_a_idx": 0, "room_b_idx": 2, "edge_type": "door"},          ← hub → pokój 2
    {"room_a_idx": 0, "room_b_idx": 3, "edge_type": "door"},
    {"room_a_idx": 0, "room_b_idx": 1, "edge_type": "door"},
    {"room_a_idx": 0, "room_b_idx": 4, "edge_type": "opening"}        ← hub → salon (otwór)
  ],
  "entry_position": {"x": 8.86, "y": 5.6},
  "boundary_edges": [...]  ← wall_type per krawędź zewnętrzna
}
```

**Co zawiera:** GEOMETRIA pokoi + GRAF sąsiedztwa wypełniony + entry_position + boundary_edges.

**Mapowanie `room_type` → kategoria:** `data/dataset_loader.py` (`ROOM_TYPE_TO_CATEGORY`):
- `1` → SYPIALNIA
- `3` → LAZIENKA
- `4` → WC
- `5`/`6` → HUB
- `7` → GARDEROBA
- `10` → SYPIALNIA (POKÓJ generic)
- `13` → PRALNIA
- `17` → SALON_ANEKS

**Pliki (27):**
- 21× PL_NL_* (Natura Life — Wrocław)
- 6× PL_TVR_* (TVR Konopnickiej — Warszawa)

**Pola edge:**
- `room_a_idx`, `room_b_idx` — indeks pokoju w `rooms[]` (lub `-1` = outside)
- `edge_type`: `"entry_door"` / `"door"` / `"opening"`

**Pola stretch (jak elastyczna jest krawędź):**
- `"FIX"` — krawędź się NIE rusza (np. ścianka w łazience z instalacjami)
- `"STRETCH"` — można rozciągać proporcjonalnie
- `"ADAPT"` — dopasowuje się do sąsiada

**Po co:**
1. **Reference dataset** dla `core/template_selector.py` — szuka rzutu o podobnej geometrii (aspect_ratio, area, n_rooms) do obrysu użytkownika
2. **Walidacja solvera** — sprawdzamy że solver dla danego obrysu generuje rozkład PODOBNY do reference
3. **Statystyki dla constraint templates** — `data/dataset_stats.py` używa tych 27 do obliczania statystyk (np. % powierzchni hub w mieszkaniach M3)

**Kiedy użyć:** w `template_selector` i przy walidacji wyników solvera.

---

## DECYZJA: KIEDY UŻYĆ KTÓREGO

| Scenariusz | Zestaw |
|------------|--------|
| Generuję NOWY rzut na obrysie z AC | **1** (constraints + solver) |
| Walidacja czy wygenerowany rzut jest sensowny | **1** (validator) + **3** (porównanie z reference) |
| Szukam najbliższego rzeczywistego rzutu do mojego obrysu | **3** (template_selector matching) |
| Buduję statystyki "ile metrów ma typowy hub w M2" | **3** (dataset_stats) |
| Potrzebuję GEOMETRII konkretnego rzutu z FP4 którego nie ma w Zestawie 3 | **2** — importuj ad-hoc z FP4 |

---

## ANTI-PATTERNS

❌ **NIE łącz Zestawu 1 z Zestawem 3 w jednym pliku.** Były próby zrobienia "v3 z constraint i geometrią razem". Nie przyniosły wartości — różne moduły potrzebują różnych rzeczy.

❌ **NIE modyfikuj Zestawu 3 ręcznie.** To dane referencyjne (rzeczywiste obtraced rzuty). Modyfikacja = utrata wiarygodności validatora.

❌ **NIE używaj Zestawu 2 jako głównego źródła grafu** — edges są placeholderem `-1`, NIE prawdziwymi danymi.

❌ **NIE dodawaj nowego pokoju do constraint template bez aktualizacji `sasiedztwo[]`** — solver wymaga że hub musi dotykać KAŻDEGO pokoju (F4/F5).

---

## SUMMARY

- **`templates/` (7 plików)** = constraints, używaj w solverze i validatorze
- **`data/plans/` (27 plików)** = real reference z geometrią + grafem, używaj w template_selector i dataset_stats
- **`rzuty/` (puste)** = niedokończony zestaw 2 z FP4, importuj ad-hoc tylko gdy potrzebujesz konkretnego brakującego rzutu
