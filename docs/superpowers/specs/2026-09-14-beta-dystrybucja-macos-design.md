# Beta dystrybucyjna FloorForge — macOS + ArchiCAD 29 (design)

> Data: 2026-09-14. Zatwierdzone przez Dawida w brainstormingu (wariant A: kontynuacja
> FloorPlan6 w miejscu; cel: dystrybucja zamkniętej bety kilku znajomym architektom).

## 1. Cel i zakres

**Cel:** znajomy architekt na macOS z ArchiCAD 29 rozpakowuje jeden zip, kopiuje dodatek
Tapir, otwiera aplikację i przechodzi ścieżkę obrys z AC → warianty → wstaw do AC,
bez instalowania Pythona, bez konsoli, bez pomocy Dawida.

**W zakresie:**
- Zakładka „Podział rzutu": mieszkania M1–M5 oraz domy (parterowe i 2-kondygnacyjne)
  z eksportem do AC (strefy, ściany, drzwi, okna, etykiety).
- Zamrożona aplikacja `.app` (PyInstaller, onedir) + custom Tapir `.bundle` w jednym zipie.
- Komunikaty błędów po polsku w GUI + log techniczny na dysku.
- Podpis ad-hoc (Gatekeeper: jednorazowe „otwórz mimo to").

**Poza zakresem (świadomie):** Windows, notaryzacja Apple, przycisk w palecie Tapir,
auto-aktualizacje, licencjonowanie użytkowników, parcelacja (Etap 1), raport PDF,
Etap 2/3, zmiana licencji AGPL (decyzja przed sprzedażą, nie przed betą).

## 2. Architektura wydania

Podział mózg/powłoka bez zmian (`docs/ROADMAP_domy.md`): mózg w Pythonie, powłoka =
Tapir. Aplikacja i AC rozmawiają przez localhost (porty 19723–19730) jak dotąd.

**Korekta 2026-09-14 (skala):** mózg wystawiony jako **lokalny serwer HTTP** za kontraktem
JSON, a GUI jest jego pierwszym klientem. Dzięki temu przyszła powłoka (własny add-on
C++ lub chmura) różni się tylko adresem URL.

- Nowy moduł `service/app.py` (stdlib `http.server` lub FastAPI — decyzja w planie;
  preferencja: stdlib, żeby nie rozszerzać zależności PyInstallera).
- Endpointy: `POST /solve` (wejście: obrys + typ + opcje → wyjście: lista wariantów w
  formacie `plan_to_contract`), `GET /health` (wersja, status), `POST /export` (wariant →
  AC przez istniejący `plan_writer`; w wersji lokalnej serwer sam gada z Tapirem).
- Serwer startuje w tle razem z GUI na losowym wolnym porcie `127.0.0.1`; GUI wywołuje
  go zamiast bezpośrednio `generate_variants`/`generate_house`. Ścieżka bezpośrednia
  zostaje dla testów i CLI.
- Długie solve'y: `POST /solve` zwraca `job_id`, `GET /jobs/{id}` daje postęp i wyniki
  częściowe (dziś progress callback w `variant_generator`). GUI pokazuje pasek postępu
  i pierwsze warianty zanim skończą się wszystkie.

Zawartość `FloorForge-beta-<wersja>.zip`:

| Plik | Źródło |
|---|---|
| `FloorForge.app` | PyInstaller onedir z `ui/main_window.py` jako entry point |
| `TapirAddOn_AC29_Mac.bundle` | build z `tapir-custom/` (CreateDoors z `libraryPart`/`oSide`/`reflected`). **Tymczasowy** — patrz sekcja 9 |
| `INSTALACJA.md` | 1 strona: gdzie skopiować bundle, jak otworzyć .app mimo Gatekeepera, jak zgłosić błąd |
| `Uruchom.command` | awaryjne uruchomienie binarki z terminala (widać stack trace) |

Wersja bety = `git describe --tags` w momencie builda, wpisana do `Info.plist`
i widoczna w tytule okna.

## 3. Tryb beta w GUI

- Zmienna środowiskowa `FLOORFORGE_BETA=1` (ustawiana w spec PyInstallera przez
  bootstrap w entry point; lokalnie można ustawić ręcznie do testów).
- W trybie beta `MainWindow` buduje **tylko** zakładkę „Podział rzutu" (dzisiejsza
  zakładka Stage 4 z istniejącym przełącznikiem dom/mieszkanie). Etapy 1–3, placeholdery
  i raport PDF nie są importowane ani dodawane do okna. Kod zostaje w repo.
- Bez flagi: okno wygląda jak dziś (wszystkie zakładki) — lokalne środowisko Dawida
  nie zmienia zachowania.
- Pasek statusu AC (nowy widget w zakładce): port, nazwa projektu (Tapir
  `GetProjectInfo`), aktywna kondygnacja (`GetStories.actStory`), przycisk „Odśwież".
  Reużywa `TapirConnection.list_instances()` / `get_project_info()` / `get_stories()`.
- Nazewnictwo po polsku w trybie beta (zakładka, przyciski, statusy). Angielskie
  stringi Stage 3 nie są ruszane (poza betą).

## 4. Komunikaty i błędy

- Każdy wyjątek z solvera, Tapira lub eksportu przechwycony na granicy handlerów GUI
  (`_generate`, `_export_to_archicad`, `_import_*`) → `QMessageBox` po polsku:
  jedno zdanie przyczyny + jedno zdanie porady. Przykłady:
  - brak AC: „Nie znaleziono ArchiCADa na portach 19723–19730. Uruchom AC z załadowanym
    dodatkiem Tapir i kliknij Odśwież."
  - Tapir bez naszych komend: „Dodatek Tapir w AC nie obsługuje CreateDoors z parametrem
    libraryPart. Zainstaluj bundle z paczki FloorForge."
  - INFEASIBLE: „Nie znaleziono układu dla tego obrysu i typu. Spróbuj inny typ lub
    powiększ obrys." (zgodne z regułą „NIE ZNALEZIONO — architekt decyduje").
- Mapowanie wyjątek → komunikat w jednym module `ui/user_errors.py`
  (funkcja `describe(exc) -> (tytuł, treść)`), testowalna bez Qt.
- Log techniczny: `~/Library/Logs/FloorForge/floorforge.log`, `RotatingFileHandler`
  (5 × 2 MB), poziom INFO, pełny traceback przy błędzie. Brak wysyłki sieciowej.
  Ścieżka do logu wyświetlana w oknie błędu.

## 5. Pakowanie

Nowy katalog `packaging/`:

- `floorforge.spec` — PyInstaller onedir → `.app`; `datas`: `templates/`, `rules/`,
  `data/plans/`; `hiddenimports` dla OR-Tools (`ortools.sat.python.cp_model`,
  `ortools.sat.*`), Shapely (`shapely._geos`), PyQt5 (`PyQt5.sip`), matplotlib backend
  `QtAgg`; ikona `packaging/icon.icns`; `Info.plist` z `CFBundleName`,
  `CFBundleShortVersionString`, `NSHighResolutionCapable`.
- `requirements-lock.txt` — `pip freeze` z działającego venv (Python 3.13, OR-Tools
  9.15.x, Shapely 2.1.x, PyQt5 5.15.11, matplotlib 3.10.x, archicad 29.3000).
- `build_release.sh` — kroki: (1) czysty venv w `packaging/.venv`, (2) `pip install -r
  requirements-lock.txt pyinstaller`, (3) `pyinstaller floorforge.spec`, (4) `codesign
  --force --deep --sign - dist/FloorForge.app`, (5) kopiowanie bundla Tapira z
  `../tapir-custom/archicad-addon/Build/RelWithDebInfo/` (błąd, jeśli brak), (6)
  `INSTALACJA.md` + `Uruchom.command`, (7) zip do `dist/FloorForge-beta-<wersja>.zip`.
  Skrypt kończy się niezerowym kodem przy każdym błędzie (`set -euo pipefail`).
- Ścieżki danych: dziś `Path(__file__).parent.parent / "templates"` i analogicznie
  `rules/` — w onedir `datas` zachowują względne położenie, więc bez zmian w kodzie.
  Jeśli w kroku smoke wyjdzie inaczej, dodać helper `core/resources.py` (`resource_root()`
  z obsługą `sys._MEIPASS`) i użyć w 3 miejscach: `template_selector.py:95`,
  `rules/_loader.py:24`, `ui/main_window.py:17`.

## 6. Testowanie

| Poziom | Co | Bramka |
|---|---|---|
| pytest | istniejący suite + `tests/test_beta_mode.py` (z `FLOORFORGE_BETA=1`: 1 zakładka, `ui.stage1_window` nieimportowany) + `tests/test_user_errors.py` (mapowanie wyjątków) | zielone przed buildem |
| smoke zamrożonej binarki | `packaging/smoke_frozen.sh` uruchamia `.app/Contents/MacOS/FloorForge --selftest`: generuje M2 na prostokącie 8×6, sprawdza ≥1 wariant, kod wyjścia 0; nie wymaga AC ani okna | zielone po każdym buildzie |
| ręczny, czyste konto | nowe konto użytkownika na Macu Dawida, instalacja wyłącznie z zipa wg `INSTALACJA.md`, przebieg obrys→warianty→AC dla mieszkania M3 i domu 2-kond. (parter + poddasze na właściwych kondygnacjach) | bramka wysyłki do znajomych |

## 7. Kolejność wdrożenia

0. **Zabezpieczenie repo:** `git push` (140 commitów), usunięcie 30 duplikatów `* 2.py`,
   pełny pytest, tag `v0.6-baseline`, aktualizacja README (stan etapów).
1. **Dom→AC live:** probe `notebooks/ac_story_switch_probe.py` z Dawidem przy AC,
   wpięcie `activate_story` (1-klik obie kondygnacje) wg
   `2026-06-22-dom-ac-story-target-multi-instance-design.md`. Bez tego domy w becie
   działają tylko na aktywnej kondygnacji.
2. **Tryb beta GUI** (sekcja 3) + błędy i log (sekcja 4).
3. **Pakowanie** (sekcja 5) + smoke (sekcja 6).
4. **Test na czystym koncie** → poprawki → wysyłka do 2–3 osób z prośbą o log przy błędzie.

## 8. Otwarte decyzje (nie blokują bety)

- Licencja: repo jest AGPL-3.0; Dawid jest właścicielem i może relicencjonować przed
  sprzedażą. Do rozstrzygnięcia przed wersją publiczną.
- Stock Tapir vs custom: beta wymaga custom builda (drzwi). Jeśli upstream Tapir przyjmie
  parametry drzwi, wrócić do stocka.

## 9. Kolejka po becie (decyzje strategiczne z 2026-09-14, poza zakresem bety)

Kolejność wg wpływu na adopcję i skalę. Nic z tego nie blokuje wysyłki bety; beta ma
zweryfikować punkt 1.

1. **Interaktywność:** przypnij pokój / zablokuj ścianę / wymuś drzwi → generuj ponownie.
   Każda blokada = dodatkowe ograniczenie CP-SAT. Pierwsza praca po becie, przed
   jakimkolwiek strojeniem benchmarku.
2. **Własna cienka powłoka zamiast forka Tapira.** Custom Tapir = utrzymanie C++ per
   wersja AC × OS bez natywności i bez obrotu obiektów (meble zamrożone). FP4_CPP ma
   gotowe: `BoundaryReader`, `PlanWriter` (ściany z kompozytem, drzwi z orientacją, otwory,
   undo), paletę. Docelowo: powłoka z FP4_CPP jako klient HTTP mózgu (sekcja 2).
   Alternatywa tańsza: upstream parametrów drzwi do Tapira (MIT, aktywny) i powrót do stocka.
3. **Mózg w chmurze** — ten sam `service/app.py` za HTTPS: znika PyInstaller, podpisy,
   Windows-build, licencjonowanie w kliencie; więcej rdzeni dla domów. Wymaga zmiany
   licencji (AGPL a hosting) i decyzji o prywatności rzutów.
4. **Czas i determinizm solvera:** stałe ziarno + 1 wątek w trybie reprodukcji, wyniki
   częściowe (pkt 1 sekcji 2), granica MVP ~160 m²/kondygnację z jasnym komunikatem.
5. **Szablony z własnych projektów biura** („User Library Mode" — spec w FP4_CPP,
   commit `b41475a`): import rzutów użytkownika jako szablony, na bazie `refs_geo`.
6. **Odchudzenie repo:** `core/` jako pakiet z testami <3 min; zamrożone etapy 1/2/3 i
   raport PDF do osobnego pakietu; `ui/main_window.py` (1475 linii) podzielony per zakładka.
