# Dom → ArchiCAD write-back (MVP) — design

> Data: 2026-06-18 (sesja: audyt MVP → budowa luki #1). Branch `feat/sfh-open-plan-day-zone`.
> Status: zaakceptowany przez Dawida (brainstorm). Następny krok: writing-plans.

## Kontekst i premisa

Audyt MVP (4 równoległe agenty, 2026-06-18) ustalił: mózg (generacja domów) i render są
gotowe (benchmark 60.0/15-16; tryb architektoniczny zaakceptowany okiem), ale **ścieżka
dom → ArchiCAD praktycznie nie istnieje** — to jedyna luka blokująca MVP „klik → rzut domu
w AC".

Stan zastany:
- **Mieszkania**: pełny pipe end-to-end (GUI „Wstaw do AC" → `bridge/plan_writer.export_plan_to_archicad`
  → Tapir): strefy, ściany, drzwi, okna, etykiety, meble.
- **Domy**: tylko offline `notebooks/ac_house_smoke.py` wpisuje strefy + ściany **parteru**
  (drzwi/okna/poddasze/meble/etykiety wyłączone). W `bridge/` NIE ma writera dla
  `TwoStoreyLayout`. GUI „Wstaw do AC" jest **wyłączone** w trybie dom (`main_window.py:663`,
  `:568`, tooltip „później (shell C++)").

## Cel

Wstawić wygenerowany dom jednorodzinny do ArchiCAD — jedną kondygnację na aktywną
kondygnację AC — reuse sprawdzonego writera mieszkań. MVP „dla Dawida" (jego maszyna +
AC + Tapir), nie dystrybucja.

## Decyzje architektoniczne (brainstorm)

1. **Mapowanie kondygnacji = 2 przebiegi, realne kondygnacje.** Tapir tworzy elementy na
   AKTYWNEJ kondygnacji AC i NIE umie jej przełączać (brak komendy story-targeting;
   `create_walls` ma `zCoordinate`, ale tylko okna/etykiety mają `floorInd`). Eksport pisze
   JEDNĄ kondygnację na raz. Użytkownik: ustaw kondygnację w AC = wybierz tę samą w GUI →
   wstaw → przełącz → wstaw.
2. **Architektura = reuse writera per-piętro (Approach A).** Nowy
   `export_house_to_archicad(layout, storey, …)` buduje per-kondygnację `FloorPlan` z
   właściwym szablonem i woła istniejący `export_plan_to_archicad`. NIE przez kontrakt JSON
   (to droga bundle — odłożona na produktyzację).
3. **Przełącznik kondygnacji w GUI ręczny** (Parter/Poddasze) — Tapir i tak nie przełącza,
   odczyt aktywnej kondygnacji z AC = zbędna komplikacja na MVP.
4. **Meble WYŁĄCZONE** (`include_furniture=False`) — zamrożone (Tapir bez rotacji), zgodnie
   z roadmapem. **Schody = strefa „Schody" + ściany** (Tapir nie ma CreateStairs; realny
   obiekt schodów architekt wstawia sam). **Drzwi = stockowy Tapir** (domyślna orientacja,
   1-klik flip), jak mieszkania; custom build użyje oSide/reflected automatycznie.

## Architektura

```
GUI (tryb dom): "Wstaw do AC" [odblokowany] + przełącznik kondygnacji (Parter/Poddasze)
   └─ export_house_to_archicad(layout: TwoStoreyLayout, storey: str, connection, include_*)   # bridge/house_writer.py (NOWY)
        ├─ wybór: rooms = layout.parter_rooms | layout.pietro_rooms
        ├─ template = load(house_single_storey | house_parter | house_pietro)   # istniejące szablony
        ├─ plan = FloorPlan(boundary=layout.boundary, template=template, rooms=rooms)
        └─ export_plan_to_archicad(plan, connection, include_furniture=False, …)   # ISTNIEJĄCY writer mieszkań, reuse 1:1
              → CreateZones / CreateWalls / CreateDoors / CreateWindows / CreateLabels (Tapir)
```

Nowy plik `bridge/house_writer.py` (nie puchnie `plan_writer.py`). Reuse: cała maszyneria
strefy/ściany/drzwi/okna/etykiety z `export_plan_to_archicad`; zachowanie zCoordinate/
aktywnej kondygnacji NIEzmienione (jeśli mieszkania siadają na aktywnej kondygnacji, dom
też — ten sam writer).

## Zakres per kondygnacja (MVP)

WŁĄCZONE: strefy (named zones), ściany działowe, drzwi (template `sasiedztwo`), okna
(fasada), etykiety. WYŁĄCZONE: meble, obiekt schodów, slaby/stropy.

## Weryfikacja / testy

1. **Offline** (`tests/test_house_writer.py`, nowy): zbuduj `TwoStoreyLayout` (jak
   `test_two_storey_render`), zawołaj `export_house_to_archicad` z MOCKIEM połączenia
   (fake TapirConnection rejestrujący wywołania) — asercje: (a) per-storey FloorPlan ma
   właściwy szablon, (b) writer dostaje pokoje wybranej kondygnacji, (c) payloady
   stref/ścian niepuste, (d) meble wykluczone, (e) parterowiec → tylko „parter". Wzorzec
   z istniejących testów eksportu mieszkań.
2. **Na żywo (Dawid w AC)** — bramka finalna: 2 przebiegi (Parter na kondygnacji parteru,
   Poddasze na kondygnacji poddasza), wzrokowa ocena rzutu. Jak przy mieszkaniach S24-25
   (kod buduje + testuje payload; Dawid waliduje w AC).

## Zakres plików

- `bridge/house_writer.py` — NOWY: `export_house_to_archicad`.
- `ui/main_window.py` — odblokuj „Wstaw do AC" w trybie dom + przełącznik kondygnacji + handler.
- `tests/test_house_writer.py` — NOWY: testy offline na mocku.
- BEZ zmian: `bridge/plan_writer.py` (reuse), generator, solver, ścieżka mieszkań.

## Ryzyka / miny (do uwzględnienia w planie)

- **Szablon `sasiedztwo` vs realny room-set.** `extract_doors` liczy drzwi z
  `template.sasiedztwo`; generowany dom (best-effort fallback, skalowane pokoje) może
  odbiegać od szablonu → część drzwi może nie powstać. MVP-akceptowalne (architekt dostawia).
  Alternatywa do rozważenia w planie: drzwi z geometrii (`infer_door_openings`, świeżo
  naprawione „jedno wejście/pokój") — ale zwraca `DoorOpening` (render), nie `DoorSegment`
  (Tapir); konwersja = osobny koszt. Decyzja w planie; domyślnie reuse template-path (jak
  mieszkania).
- **Orientacja drzwi/otwory** wymaga custom Tapir build dla oSide/reflected/libraryPart;
  stock = domyślna orientacja (1-klik flip). Akceptowalne MVP.
- **Aktywna kondygnacja / zCoordinate**: reuse zachowania mieszkań; jeśli mieszkania
  wymagają konkretnego ustawienia, udokumentować w plan/handoff dla Dawida.
- **Live-only weryfikacja**: brak AC u Claude → offline testy + handoff do Dawida.

## Poza zakresem (YAGNI)

- Kontrakt→Tapir (bundle/produktyzacja).
- Slaby/stropy, meble w AC, obiekt schodów.
- Auto-przełączanie/odczyt aktywnej kondygnacji (Tapir nie umie).
- Pakowanie (PyInstaller), C++ shell, przycisk w AC — produktyzacja.
- Bliźniak/szeregowiec, perf dużych L/T — osobne wątki.
