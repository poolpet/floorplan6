# FloorForge.bundle — jeden dodatek w Dodatkach AC (design)

> Data: 2026-09-15. Zastępuje formę dystrybucji ze specu
> `2026-09-14-beta-dystrybucja-macos-design.md` (osobny `.app` + bundle Tapira + instrukcja).
> Decyzja Dawida: instalacja = skopiowanie JEDNEGO bundla do `Dodatki`, zero innych czynności.
> Wzorzec: `~/Desktop/CLT/clt-panels` (cmake → bundle → kopia → ad-hoc codesign; działa bez
> Developer ID). Kod C++ trafia do `FloorPlan6/addon/` (opcja 1, decyzja Dawida).

## 1. Cel i zakres

**Cel:** tester kopiuje `FloorForge.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`,
uruchamia AC, wybiera menu **FloorForge → Podział rzutu** i dostaje okno FloorForge połączone
z tą instancją AC. Nic więcej do zainstalowania ani klikania.

**W zakresie:**
- Nowy katalog `FloorPlan6/addon/` = kopia `tapir-custom/archicad-addon/` (MIT, nota
  licencyjna) z modyfikacjami: tożsamość FloorForge (MDID, nazwa, identyfikator), przestrzeń
  komend `FloorForgeCommand`, nowe menu uruchamiające zagnieżdżony proces Pythona.
- Zamrożony Python (dzisiejszy build PyInstaller onedir) osadzony w
  `FloorForge.bundle/Contents/Resources/FloorForge/`.
- `packaging/build_release.sh` buduje bundle (cmake + PyInstaller + codesign ad-hoc + zip)
  z bramką z zipa; `packaging/install_local.sh` = odpowiednik `tools/install.sh` z CLT.
- Python: połączenie z instancją AC wskazaną przez add-on (nazwa projektu), przestrzeń komend
  z jednej stałej.
- `INSTALACJA.md` i `CHECKLIST_TEST.md` przepisane pod bundle.

**Poza zakresem:** Windows (`.apx`), notaryzacja, natywna paleta w AC (mózg nadal w oknie PyQt),
przepięcie GUI na klienta HTTP, zmiany w `core/`.

## 2. Układ bundla

```
FloorForge.bundle/Contents/
  Info.plist                  CFBundleIdentifier pl.d7studio.floorforge, CFBundleName FloorForge,
                              CFBundleShortVersionString = git describe
  PkgInfo                     z DevKit (jak CLT)
  MacOS/FloorForge            add-on C++ (fork Tapira: komendy JSON + menu + spawn)
  Resources/                  zasoby AC skompilowane z addon/Sources/R*/ (MDID, STR#, GICN)
  Resources/FloorForge/       PyInstaller onedir: FloorForge (exe), _internal/, templates/, rules/, data/plans/
```

Tożsamość:
- `MDID` 879970669 / **416370978** (zarejestrowany FloorForge, z `FloorPlan4_CPP/RFIX/FloorPlan4Fix.grc`).
- `AddOnName` w CMake: `FloorForge` (nie `TapirAddOn_AC29_Mac`); `AddOnVersion.hpp` = wersja
  z `git describe` wstrzyknięta przez CMake (`-DFLOORFORGE_VERSION=…`).
- `CommandNamespace` w `addon/Sources/CommandBase.cpp`: `"FloorForgeCommand"`.
- Menu Tapira (paleta skryptów, „Check for updates", „About Tapir") **usunięte z menu**; kod
  palety może zostać w źródłach, ale nie jest rejestrowany. Zostają: **„FloorForge → Podział
  rzutu"** i **„FloorForge → O FloorForge…"** (dialog z wersją i ścieżką logu).

## 3. Menu → proces Pythona

Handler menu „Podział rzutu" (`addon/Sources/FloorForgeLauncher.cpp`, nowy plik):
1. Ścieżka do exe: `<bundle>/Contents/Resources/FloorForge/FloorForge` (bundle przez
   `ACAPI_GetOwnResModule` → `CFBundleCopyBundleURL` lub `dladdr`; jak w Tapirze przy
   szukaniu skryptów).
2. Env dla procesu: `FLOORFORGE_BETA=1`, `FLOORFORGE_VERSION=<ADDON_VERSION>`,
   **`FLOORFORGE_AC_PORT=<port z ACAPI_Command_GetHttpConnectionPort>`** (add-on zna port JSON
   własnej instancji AC — deterministyczny cel bez skanowania i bez nazw projektów),
   `FLOORFORGE_LAUNCHED_FROM_AC=1`.
3. Spawn przez `GS::Process::Create (command, argv, GS::Process::CreateNoWindow, …)` (ten sam
   mechanizm, którym paleta Tapira uruchamia skrypty) — bez czekania, bez przechwytywania
   stdout (log idzie do pliku Pythona).
4. Jeśli proces z poprzedniego kliknięcia żyje (`GS::Process::IsAlive` / pid w pamięci
   add-onu), nie uruchamiaj drugiego: pokaż komunikat „FloorForge jest już otwarty" (okno
   PyQt samo wraca na wierzch przy starcie — podniesienie cudzego okna z AC nie jest w zakresie).
5. Błąd spawnu → `DGAlert` po polsku z pełną ścieżką exe i poradą „przeinstaluj bundle".

## 4. Zmiany w Pythonie

- `bridge/tapir_connection.py`: `TAPIR_NAMESPACE = "FloorForgeCommand"` (jedna stała; grep
  potwierdza 3 użycia w bridge + 2 w notebooks). Notebooki `ac_story_switch_probe.py`,
  `ac_story_diag.py` czytają stałą zamiast literału.
- `TapirConnection.connect()`: jeśli env `FLOORFORGE_AC_PORT` ustawione i poprawne → `use_port()`
  na tym porcie (bez skanu, bez preferencji zaznaczenia); port martwy lub env niepoprawne →
  dotychczasowy skan z ostrzeżeniem w logu. `list_instances()` i picker eksportu domu bez
  zmian (multi-instance nadal obsługiwane), ale `AcStatusWidget` i eksport domu preferują
  port z env, gdy jest wśród wykrytych.
- `floorforge_app.py`: bez zmian funkcjonalnych (env już obsługuje). `--selftest` zostaje
  bramką builda.
- `ui/user_errors.py`: komunikat „Nie znaleziono ArchiCADa…" dostaje wariant, gdy
  `FLOORFORGE_LAUNCHED_FROM_AC=1`: „Uruchomiono z AC, ale AC nie odpowiada na porcie
  JSON — sprawdź Opcje → Ustawienia → JSON API (port 19723) i kliknij Odśwież."

## 5. Build i instalacja

`packaging/build_release.sh` (przepisany; `set -euo pipefail`, log przez `tee`, praca w
`$TMPDIR` przez iCloud):
1. `VER=$(git describe --tags --always --dirty)`; asercja niepusta.
2. **Python:** PyInstaller onedir (`packaging/floorforge.spec`, cel `COLLECT` bez `BUNDLE`) →
   `$WORK/py/FloorForge/`.
3. **Add-on:** `cmake -S addon -B $WORK/addon-build -DAC_API_DEVKIT_DIR="…/API archicad"
   -DFLOORFORGE_VERSION=$VER` + `cmake --build` → `$WORK/addon-build/RelWithDebInfo/FloorForge.bundle`.
4. **Złożenie:** `ditto $WORK/py/FloorForge "$BUNDLE/Contents/Resources/FloorForge"`.
5. **Podpis:** `codesign --force --deep --sign - "$BUNDLE"` (ad-hoc, jak CLT
   `install_to_archicad`), `codesign --verify --deep --strict` fatalny.
6. **Zip:** `ditto -c -k --keepParent --norsrc --noextattr` → `FloorForge-<VER>.zip`.
7. **Bramka z zipa:** rozpakuj do `$WORK/verify`, `codesign --verify --deep --strict`,
   `Contents/Resources/FloorForge/FloorForge --selftest` → `SELFTEST OK`, zero `._*`,
   `Contents/MacOS/FloorForge` istnieje i jest Mach-O, `Info.plist` ma
   `CFBundleIdentifier=pl.d7studio.floorforge`. Dopiero potem `packaging/dist/` ← zip.
8. `packaging/install_local.sh`: buduje (lub bierze gotowy bundle z `dist`), usuwa stary
   `Dodatki/FloorForge.bundle`, kopiuje nowy, `codesign --force --sign -`, przypomina
   „Cmd+Q i start AC". Usuwa też **`TapirAddOn_AC29_Mac.bundle` z Dodatków, jeśli jest** (dwa
   add-ony z tymi samymi komendami = niezdefiniowane zachowanie; ostrzeżenie w README CLT)
   oraz **`FloorPlan4.bundle`** (ten sam Local ID 416370978 — dwa bundle z jednym MDID nie mogą
   współistnieć); oba usuwane z jawnym ostrzeżeniem na konsoli.

`packaging/smoke_frozen.sh`: rozpakowuje najnowszy zip i uruchamia `--selftest` z
`Contents/Resources/FloorForge/FloorForge` (ścieżka zmieniona).

## 6. Testowanie

| Poziom | Co | Bramka |
|---|---|---|
| pytest | istniejące + `tests/test_ac_port_env.py` (connect po `FLOORFORGE_AC_PORT`: port żywy → use_port bez skanu; port martwy → skan + log; env niepoprawne → skan) + test stałej przestrzeni komend (żaden plik poza `tapir_connection.py` nie zawiera literału `"TapirCommand"`/`"FloorForgeCommand"`) | zielone przed buildem |
| C++ | brak testów jednostkowych (jak Tapir); kompilacja z `-Werror` jak CLT | build przechodzi |
| smoke z zipa | jak dziś, ścieżka do exe w bundlu | `SMOKE OK` po każdym buildzie |
| **spike kwarantanny (PIERWSZY krok planu)** | zbudować bundle, spakować, pobrać zip na koncie „beta-test" przeglądarką (kwarantanna!), rozpakować Finderem, skopiować do Dodatków, uruchomić AC, kliknąć menu. Oczekiwane: AC ładuje bundle, menu widoczne, okno FloorForge się otwiera. | jeśli FAIL → STOP, raport, decyzja Dawida (notaryzacja / `xattr` w instrukcji) |
| ręczny, czyste konto | `CHECKLIST_TEST.md` przepisany: 1) zip → folder z JEDNYM `FloorForge.bundle`; 2) kopia do Dodatków, start AC; 3) menu FloorForge widoczne; 4) „Podział rzutu" → okno z tytułem `FloorForge <wersja>` i paskiem `AC port … · <projekt>` **bez klikania Odśwież**; 5) drugie kliknięcie menu → komunikat „już otwarty"; 6–13) jak dziś (M3 → AC, dom obie kondygnacje, błąd bez AC, log). | bramka wysyłki |

## 7. Kolejność wdrożenia

0. Spike kwarantanny na minimalnym bundlu (kopia Tapira z nowym MDID + menu, które
   uruchamia zamrożonego Pythona z obecnego `dist`) — zanim ruszy reszta.
1. `addon/`: kopia forka, tożsamość FloorForge, przestrzeń komend, menu + launcher, usunięcie
   menu Tapira, `LICENSE` + `NOTICE`.
2. Python: stała przestrzeni, `FLOORFORGE_AC_PORT`, komunikat błędu, testy.
3. `packaging/`: spec PyInstallera bez `BUNDLE`, `build_release.sh`, `install_local.sh`,
   `smoke_frozen.sh`, usunięcie `Uruchom.command`/`VERSION`/`make_icon` (ikona bundla = `.icns`
   w `RFIX.mac` jak CLT `ArchiCADPlugin.icns`).
4. Docs: `INSTALACJA.md` (3 zdania), `CHECKLIST_TEST.md`, `README.md`, `STATE.md`.
5. Bramka ręczna na czystym koncie → tag `v0.7-beta1` → FF do `main` → wysyłka.

## 8. Ryzyka i decyzje otwarte

- **Kwarantanna zagnieżdżonego exe:** AC ładuje bundle jak CLT (ad-hoc), ale proces Pythona
  jest uruchamiany przez `posix_spawn` z plików z kwarantanną. Spike w kroku 0 rozstrzyga.
  Jeśli macOS blokuje: plan B = `xattr -dr com.apple.quarantine` wykonywany przez add-on na
  własnym bundlu przy pierwszym uruchomieniu (add-on ma prawo do własnych plików) — do
  decyzji Dawida, bo to obejście, nie rozwiązanie.
- **Rozmiar bundla ~200 MB** (OR-Tools + Qt + matplotlib) w Dodatkach; AC ładuje tylko
  `MacOS/FloorForge`, reszta leży na dysku. Akceptowalne dla bety.
- **Jeden MDID, jeden bundle:** `FloorPlan4.bundle` (ten sam Local ID) nie może być w
  Dodatkach razem z FloorForge. `install_local.sh` usuwa go z ostrzeżeniem.
- **Wersja AC:** bundle przypięty do AC29; nowa wersja AC = rebuild z nowym DevKit.
- **Licencja:** fork Tapira MIT → `addon/LICENSE` (oryginał) + `addon/NOTICE` (co zmieniono).
  Repo FP6 pozostaje AGPL na czas bety (decyzja przed sprzedażą bez zmian).

## 9. Język interfejsu (decyzja Dawida 2026-09-15, wieczór)

Beta ma trafić do testerów spoza Polski → **wszystkie stringi widoczne dla użytkownika po
angielsku** (jeden zestaw; przełącznik PL/EN = po becie, jeśli będzie potrzebny):
- GUI (tryb beta i domyślny): etykiety przycisków, zakładka „Room layout", pasek statusu AC,
  komunikaty błędów (`ui/user_errors.py`), dialogi eksportu domu (picker instancji, story-guard,
  „Insert both storeys (auto-switch in Archicad)"), placeholdery, tytuł okna.
- Add-on C++: menu „FloorForge → Room layout", „About FloorForge…", alerty launchera, dialog About.
- Log techniczny może zostać mieszany (nie jest dla testera).
- Dokumentacja dla testera: `packaging/INSTALL.md` (EN) + `packaging/INSTALACJA.md` (PL), oba w zipie.
  `CHECKLIST_TEST.md`, `STATE.md`, spec/plan — po polsku (dla właściciela).
- Testy: asercje na fragmenty tekstu przepięte na angielskie; reguła „polskie stringi" z
  Global Constraints planu zastąpiona przez „angielskie stringi widoczne dla użytkownika".
