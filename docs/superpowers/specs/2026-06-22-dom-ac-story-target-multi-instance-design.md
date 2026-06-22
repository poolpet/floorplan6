# Dom → ArchiCAD: deterministyczny target instancji + story-guard + okna — design

> Data: 2026-06-22. Branch `feat/sfh-open-plan-day-zone` (zmergowany do `main`, FF).
> Status: PROPOZYCJA — czeka na OK Dawida (B2). Następny krok po OK: writing-plans → TDD.
> Zakres: WYŁĄCZNIE warstwa AC-target / Tapir / bridge / GUI. **Mózg ZAMROŻONY** (zero
> zmian w solverze, benchmarku, kalibracji, room-secie, szablonach generowania).

## Kontekst i bloker

Po S18-cz.3 dom→AC write-back działa na poziomie kodu (`bridge/house_writer.py` +
`export_plan_to_archicad` reuse; `test_house_writer`+`test_house_export_gui` 6/6 zielone).
Live-verify Dawida (S19): **PARTER ✅ wchodzi poprawnie** (strefy/ściany/drzwi-łuki/okna/
etykiety, układ zaakceptowany okiem). **PODDASZE ❌ nie pojawia się** — Tapir zwraca GUID-y
(API „sukces"), ale w AC nie widać; status bar: `7 stref + 14 ścian + 0 drzwi + 0 okien +
7 etykiet`.

Root cause zawężony (potwierdzony w kodzie + live-research API Tapira, 2026-06-22):

1. **Brak story-targetingu (fakt kodowy).** `create_zones` (`tapir_connection.py:168`,
   `referencePosition`) i `create_walls` (`:343`, `zCoordinate` = wysokość Z, **nie** indeks
   story) lecą na **aktywną kondygnację** podpiętej instancji. Tylko `create_labels` zna
   `floorInd`. `SetActiveStory` nie istnieje. To **świadomy design 2-pass** (user przełącza
   kondygnację ręcznie), ale **bez żadnego zabezpieczenia** — nic nie pilnuje, że aktywna
   kondygnacja zgadza się z wyborem w GUI.
2. **Mina #1 — multi-instance.** `TapirConnection._scan_for_archicad` (`:59`) jest singletonem
   preferującym instancję „z zaznaczeniem". Przy >1 instancji cel eksportu jest
   **niedeterministyczny** — parter i poddasze mogą trafić do różnych dokumentów.
3. **Mina #2 — okna 0.** `get_all_walls` (`:181`) stoi na `GetElementsByType("Wall")`; gdy ta
   zwróci 0 → `[]` → pipeline okien (`plan_writer.py:219`) = 0 okien.

## Cel sesji (definicja „zrobione")

Eksport realnego domu 2-kond. do **JEDNEJ, znanej** instancji AC: parter i poddasze na
**właściwych kondygnacjach**, ze strefami / ścianami / oknami / etykietami. Drzwi poddasza
mogą być niepełne (znany MVP-gap). Live-verify potwierdza Dawid.

## Fakty z żywego AC (research 2026-06-22, NIE zgadywanie)

Sprawdzone na 2 otwartych instancjach (19723 `test.pln`, 19724 `12_Kamienica_Zagrodowa`)
przez **nasz** stack (`archicad` py + zainstalowany Tapir Add-On), read-only:

- **Multi-instance realny** — 2 instancje jednocześnie (dokładnie scenariusz blokera).
- **Tapir `GetProjectInfo`** (AddOn) → `projectName` + `projectPath` (np. „12_Kamienica_Zagrodowa").
  Standardowe `GetProjectInfo` NIE istnieje w naszym wrapperze — używamy **Tapirowego**.
  → źródło „port → nazwa dokumentu" dla pickera.
- **Tapir `GetStories`** (AddOn) → `actStory` (indeks aktywnej), `firstStory`, `lastStory`,
  `stories[]` (index/name/level). 19724: `actStory=0`, idx0=Parter, idx1=Poddasze (3.15 m),
  idx2="" (5.65 m). 19723: idx0=Parter, idx1/2 = "". → fundament story-guarda.
- **`GetElementsByType("Wall")`** przez nasz stack zwraca **73 (19723) / 37 (19724)**, NIE 0.
  Schemat komendy: opcjonalne `filters` (m.in. `OnActualFloor`) + `databases`, default null,
  zwraca elementy **„on the plan"** = scope **aktywnej bazy/okna planu**. → „0 ścian → 0 okien"
  było **stanem aktywnego okna/story** (aktywne okno nie było właściwym planem piętra), nie
  zepsutym wywołaniem.
- **Story-target głębszy (poza MVP):** `SetDetailsOfElements` ma pole `floorIndex` (retarget
  elementu na konkretną story po utworzeniu); `ChangeWindow` przełącza aktywne okno/story. →
  kandydat na „1-klik obie kondygnacje" bez ręcznego przełączania — **odłożony, do osobnej
  decyzji Dawida**.

## Decyzje architektoniczne

1. **Picker instancji w GUI** (decyzja Dawida 2026-06-22). `TapirConnection`:
   `list_instances()` (skan portów → `[{port, projectName, projectPath}]` przez Tapir
   `GetProjectInfo`, świeże połączenie per port — bez mutacji singletona) + `use_port(port)`
   (połącz z **jawnym** portem, **bez** prefer-selection). Przy eksporcie domu: 0 instancji →
   błąd; 1 → użyj jej; >1 → dialog wyboru „port — nazwa". Wybrany port zapamiętany na
   `MainWindow` (`_ac_target_port`, pre-select przy 2. przebiegu). **Zawsze** loguj port +
   nazwę w statusie/komunikacie. Ścieżka mieszkań NIETKNIĘTA (auto-connect zostaje).
2. **Story-guard (twarde ostrzeżenie)** przed `export_house_to_archicad`: czytaj
   `GetStories.actStory`. Mapowanie po **INDEKSIE** (nazwy bywają puste): GUI „Parter" ↔
   `actStory == firstStory`; GUI „Poddasze" ↔ `actStory > firstStory`. Mismatch → modal z
   jasnym komunikatem („Aktywna kondygnacja AC = '<name>' (idx N), wybrałeś '<storey>' —
   przełącz kondygnację w AC"). Projekt 1-story (`lastStory == firstStory`) + „Poddasze" →
   blok („projekt jednokondygnacyjny — nie ma poddasza"). **Override** świadomym
   potwierdzeniem („Wstawić mimo to?", default Anuluj) — żeby nie zatrzasnąć przy nietypowej
   strukturze story.
3. **AUTO-SWITCH story (decyzja Dawida 2026-06-22) — 1-klik wstawia OBIE kondygnacje.**
   Eksport sam ustawia aktywną story na docelową PRZED tworzeniem elementów → cały istniejący
   writer (strefy auto-fill + ściany + okna `GetElementsByType` active-DB) ląduje na właściwej
   story (to programowa wersja sprawdzonego ręcznego 2-pass). **Staged (ryzyko/determinizm):**
   - **Core (Task 1-2, offline-solidne):** picker instancji + story-guard + ręczny 2-pass jako
     baza (parter już tak działa). Odblokowuje dom→AC NIEZALEŻNIE od auto-switch.
   - **Auto-switch (Task 3, walidowany LIVE z Dawidem):** `activate_story(tapir, target_index)`
     przełącza aktywną story; po przełączeniu **weryfikacja** `GetStories.actStory==target`
     (inaczej → fallback na story-guard, NIGDY ślepy zaułek). Button „Wstaw cały dom" pętli
     story=[parter, (poddasze)] z auto-switch każdej.
   - **Mechanizm (research 2026-06-22):** `ChangeWindow(navigatorItemId story z ProjectMap)`
     — komenda + nav-itemy potwierdzone, ale **dokładny kształt param finicky offline**
     (schema-reject `#/navigatorItemId` z naszego stacku I z MCP) → **nailing live**.
     Alternatywa: `SetDetailsOfElements(floorIndex=target)` retarget po utworzeniu (1 komenda,
     czysta schema; ryzyko: czy auto-zone przeżywa przeniesienie — live). Index→nav-item:
     ProjectMap StoryItems top-down → `reversed` = idx rosnące (Parter=idx0); mapowanie po
     nazwie pomocniczo. **„Create-lands-on-target" niewryfikowalne offline bez tworzenia
     elementów w żywym projekcie Dawida → walidacja w handoffie.**
4. **Okna.** Primary fix = determinizm instancji (#1) + poprawna aktywna story (#2-guard):
   gdy aktywna story = piętro które piszemy, `GetElementsByType` (active-DB) zwraca ściany
   właściwego piętra → okna mają do czego się pinać. Secondary = robustness `get_all_walls`:
   **log/ostrzeżenie gdy 0 ścian** zamiast cichego `[]` (diagnostyka, nie ciche zero okien).
   **OTWARTE PYTANIE (niżej)** rozstrzygane live w kroku okien — może nie być w pełni
   zamknięte w tej sesji (najtrudniejszy, live-zależny krok).
5. **Diag `notebooks/ac_story_diag.py`** (już istnieje, filtruje `DOM-*`, skanuje porty):
   dodać **`actStory` + `projectName` per port** i jawną linię „DOM-* na porcie X, story Y".
   Odpala Dawid **od razu po eksporcie, PRZED undo**.
6. **Drzwi poddasza (0)** = znany MVP-gap (`template.sasiedztwo` vs realny room-set). **NIE
   naprawiamy** w tej sesji. Tylko odnotowane.

## OTWARTE PYTANIE (B5 — do rozstrzygnięcia LIVE w kroku okien, nie blokuje 1-3)

Parter dostał okna, poddasze 0 — **dla tego samego domu**. Do czego pinają się okna domu?
`export_plan_to_archicad` podpina okna do **istniejących ścian AC** (`get_all_walls`). Pytanie:
czy eksport domu tworzy ściany **ZEWNĘTRZNE** (obrys), czy tylko **działowe**? Jeśli poddasze
nie ma ścian obrysu na swojej story (parter ma, bo np. obrys parteru istnieje), okna piętra
nie mają hosta → 0 niezależnie od scope. **Rozstrzygnięcie:** live-repro (sonda + Dawid) w
kroku 4 → dopiero wtedy właściwy fix (robust retrieval vs tworzenie ścian obrysu vs pin do
ścian działowych). NIE zgaduję teraz (B3 — nie zmieniam zachowania na ślepo).

## Architektura (co dotykamy)

- `bridge/tapir_connection.py` — DODAJ: `list_instances()`, `use_port(port)`, `get_stories()`,
  `get_project_info()`. Istniejący auto-`connect()` (mieszkania) **bez zmian**.
- `ui/main_window.py` — `_export_house_to_archicad`: picker (gdy >1) + story-guard PRZED
  eksportem + przekaż wybrane `tapir` do `export_house_to_archicad(..., tapir=)`; status/komunikat
  z portem+nazwą. Mała funkcja-helper guarda (czysta logika) wydzielona do testów.
- `bridge/house_writer.py` — już przyjmuje `tapir=` (`:20`); przekazujemy picker-bound connection.
- `notebooks/ac_story_diag.py` — + actStory/projectName per port.
- `bridge/plan_writer.py` — `get_all_walls` w `tapir_connection` log gdy 0 (drobne; **NIE** psuć
  ścieżki mieszkań — tylko diagnostyka/log).

## Zakres / Poza zakresem

**In:** picker (det. instancji), story-guard, **auto-switch story (Task 3, live-validated)**,
diag-enhancement, okna-robustness/log, live-handoff. **Auto-switch ma bonus:** active story =
docelowa → `GetElementsByType` (active-DB) zwraca ściany właściwego piętra → prawdopodobnie
domyka mine #2 (okna poddasza) „za darmo".
**Out (YAGNI / kolejka):** drzwi-poddasze fix, meble, slaby/stropy, obiekt schodów, bundle/C++
shell, picker dla mieszkań (mieszkania działają — nie ruszamy).

## Weryfikacja / testy

1. **Offline (pytest, bez AC — monkeypatch/spy):**
   - `list_instances()` parsuje `[{port, projectName}]` z fake'owego skanu (monkeypatch
     `ACConnection.connect` + Tapir `GetProjectInfo`).
   - **story-guard = czysta funkcja** `check_active_story(act, first, last, gui_storey) ->
     (ok, msg)`: parter↔first OK; poddasze↔>first OK; poddasze na 1-story → blok; mismatch → blok.
     Pełne pokrycie tabelą przypadków, zero AC.
   - GUI dispatch (jak `test_house_export_gui`): wybrany port → `export_house_to_archicad`
     dostaje właściwe `tapir`; guard-mismatch → brak wywołania eksportu.
2. **Live (Dawid, bramka finalna):** 1 wybrana instancja; parter (AC=parter, GUI=Parter) →
   wstaw; poddasze (AC=poddasze, GUI=Poddasze) → wstaw; `ac_story_diag` potwierdza DOM-PARTER-*
   na story 0 i DOM-PODDASZE-* na story 1, oba na tym samym porcie.

## Miny

- **Singleton:** `use_port` musi nadpisać `_active_port`+`_conn` i NIE rescanować; `list_instances`
  nie mutuje singletona (świeże połączenia). Mieszkania (`connect()` auto) bez regresji.
- **Puste nazwy story** (idx2 ''): guard mapuje po INDEKSIE, nazwa pomocniczo w komunikacie.
- **GetStories/GetProjectInfo = Tapir AddOn** (nie standard) — zweryfikowane w naszym stacku
  2026-06-22; handoff potwierdza na maszynie Dawida (ten sam Tapir).
- **Okna** mogą zostać niepełne po tej sesji (OTWARTE PYTANIE) — „done" dopuszcza, priorytet =
  poddasze WIDOCZNE na właściwej story (strefy/ściany/etykiety).
