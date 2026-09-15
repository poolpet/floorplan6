# FloorForge.bundle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeden `FloorForge.bundle` skopiowany do `Dodatki` ArchiCADa 29 daje menu „FloorForge → Podział rzutu", które otwiera okno FloorForge połączone z tą instancją AC. Zero innych czynności instalacyjnych.

**Architecture:** Kopia forka Tapira (`tapir-custom/archicad-addon`, MIT) ląduje w `FloorPlan6/addon/` z tożsamością FloorForge (MDID 879970669/416370978, przestrzeń komend `FloorForgeCommand`) i nowym menu, którego handler uruchamia zamrożonego Pythona (PyInstaller onedir) osadzonego w `Contents/Resources/FloorForge/` tego samego bundla, przekazując port JSON instancji AC w env. Build składa bundle w `$TMPDIR` (iCloud), podpisuje ad-hoc, pakuje i weryfikuje z zipa. Mózg (`core/`) nietknięty; GUI PyQt bez zmian funkcjonalnych.

**Tech Stack:** C++20 + ArchiCAD API DevKit 29 (`API archicad/Support`), CMake ≥ 3.17 (narzędzia Tapira `Tools/CMakeCommon.cmake`), `GS::Process`, PyInstaller 6.22.3 (Python 3.13), bash, `codesign`, `ditto`.

**Spec:** `docs/superpowers/specs/2026-09-15-floorforge-bundle-design.md` (zastępuje formę dystrybucji z `2026-09-14-beta-dystrybucja-macos-design.md`).

## Global Constraints

- Mózg zamrożony: zero zmian w `core/` (spec §1).
- Kod C++ = kopia **working tree** `tapir-custom/archicad-addon/` (zawiera niezacommitowane patche: `Sources/ExtendedElementCommands.cpp` z parametrami drzwi i `Tools/CMakeCommon.cmake` z poprawką CMake 4.x). Nota MIT w `addon/LICENSE` + `addon/NOTICE` (spec §8).
- Tożsamość: MDID `879970669` / `416370978`; `CFBundleIdentifier` `pl.d7studio.floorforge`; nazwa bundla `FloorForge.bundle`; przestrzeń komend `"FloorForgeCommand"` w jednym miejscu (`addon/Sources/CommandBase.cpp`) i jednej stałej Pythona (`bridge/tapir_connection.py: TAPIR_NAMESPACE`) (spec §2, §4).
- Env przekazywane procesowi: `FLOORFORGE_BETA=1`, `FLOORFORGE_VERSION`, `FLOORFORGE_AC_PORT`, `FLOORFORGE_LAUNCHED_FROM_AC=1` (spec §3).
- Menu Tapira (paleta, „Check for Updates", `VersionChecker` z zapytaniem do GitHuba przy starcie) NIE jest rejestrowane (spec §2).
- Build: `set -euo pipefail`, praca w `$TMPDIR`, ad-hoc `codesign --force --deep --sign -`, bramka wyłącznie na artefakcie rozpakowanym z zipa, `packaging/dist/` ruszany dopiero po przejściu bramki (spec §5).
- Wszystkie nowe stringi widoczne dla użytkownika po polsku. Commity po polsku z prefiksem `feat/fix/build/docs/test` i stopką:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8`.
- `git add` tylko jawnych ścieżek (sync odtwarza pliki `* 2.*`, są w `.gitignore`).
- Testy Pythona: `cd FloorPlan6 && source venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest <pliki> -q -p no:cacheprovider`. Pełna suita ≈ 70 min — tylko raz, w Task 6.
- Build C++: `cmake -S addon -B <dir> -DAC_VERSION=29 -DAC_API_DEVKIT_DIR="/Users/dawidcwiertniewicz/Desktop/claude code/API archicad/Support" -DFLOORFORGE_VERSION=<ver> && cmake --build <dir> --config RelWithDebInfo` (DevKit dla narzędzi Tapira = katalog `Support`, nie jego rodzic).

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `addon/` (kopia `tapir-custom/archicad-addon/` bez `Build/`, `Examples/`, `Test/`) | add-on C++ |
| `addon/CMakeLists.txt` | nazwa `FloorForge`, `FLOORFORGE_VERSION` → definicja kompilatora |
| `addon/Tools/CMakeCommon.cmake` | identyfikator `pl.d7studio.floorforge`, wersja w plist z `FLOORFORGE_VERSION` |
| `addon/Sources/AddOnVersion.hpp` | `ADDON_VERSION` z definicji kompilatora, fallback `"dev"` |
| `addon/Sources/CommandBase.cpp` | `CommandNamespace = "FloorForgeCommand"` |
| `addon/Sources/RFIX/AddOnFix.grc` | MDID FloorForge |
| `addon/Sources/RINT/AddOn.grc` | nazwa, opis, menu „FloorForge", dialog „O FloorForge" |
| `addon/Sources/ResourceIds.hpp` | `ID_ADDON_MENU_LAUNCH` |
| `addon/Sources/FloorForgeLauncher.{hpp,cpp}` | ścieżka exe w bundlu, env, spawn, „już otwarty", alerty |
| `addon/Sources/AddOnMain.cpp` | rejestracja tylko menu FloorForge, bez palety/VersionChecker |
| `addon/LICENSE`, `addon/NOTICE` | MIT Tapira + lista zmian |
| `bridge/tapir_connection.py` | `TAPIR_NAMESPACE`, `connect()` z `FLOORFORGE_AC_PORT` |
| `notebooks/ac_story_switch_probe.py`, `notebooks/ac_story_diag.py` | import stałej zamiast literału |
| `ui/user_errors.py` | wariant komunikatu przy `FLOORFORGE_LAUNCHED_FROM_AC` |
| `packaging/floorforge.spec` | bez `BUNDLE` (onedir `COLLECT`) |
| `packaging/build_release.sh` | PyInstaller + cmake + złożenie bundla + podpis + zip + bramka |
| `packaging/smoke_frozen.sh` | selftest z bundla rozpakowanego z zipa |
| `packaging/install_local.sh` | instalacja do Dodatków (wzór CLT `tools/install.sh`) |
| `packaging/INSTALACJA.md`, `packaging/CHECKLIST_TEST.md`, `README.md`, `docs/STATE.md` | dokumentacja |
| Usuwane: `packaging/Uruchom.command`, `packaging/make_icon.py`, `packaging/icon.icns` | stara forma dystrybucji |
| `tests/test_ac_port_env.py`, `tests/test_command_namespace.py`, `tests/test_user_errors.py` (rozszerzenie) | testy |

---

### Task 1: `addon/` — kopia forka Tapira z tożsamością FloorForge i menu uruchamiającym proces

**Files:**
- Create: `addon/**` (kopia), `addon/LICENSE`, `addon/NOTICE`, `addon/Sources/FloorForgeLauncher.hpp`, `addon/Sources/FloorForgeLauncher.cpp`
- Modify: `addon/CMakeLists.txt`, `addon/Tools/CMakeCommon.cmake:185-215`, `addon/Sources/AddOnVersion.hpp`, `addon/Sources/CommandBase.cpp:7`, `addon/Sources/RFIX/AddOnFix.grc:3-6`, `addon/Sources/RINT/AddOn.grc`, `addon/Sources/ResourceIds.hpp`, `addon/Sources/AddOnMain.cpp`
- Modify: `.gitignore` (+ `addon/Build/`, `addon/build/`)

**Interfaces:**
- Produces: bundle `FloorForge.bundle` z `Contents/MacOS/FloorForge`, menu „FloorForge → Podział rzutu" i „FloorForge → O FloorForge…"; handler uruchamia `<bundle>/Contents/Resources/FloorForge/FloorForge` z env `FLOORFORGE_BETA=1`, `FLOORFORGE_VERSION=<ADDON_VERSION>`, `FLOORFORGE_AC_PORT=<port>`, `FLOORFORGE_LAUNCHED_FROM_AC=1`. Komendy JSON w przestrzeni `FloorForgeCommand`. Definicja kompilatora `FLOORFORGE_VERSION` (string) ustawiana przez CMake.

- [ ] **Step 1: Kopia forka (working tree, z patchami)**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
rsync -a --exclude 'Build/' --exclude 'Examples/' --exclude 'Test/' --exclude '.DS_Store' \
  "../tapir-custom/archicad-addon/" addon/
cp ../tapir-custom/LICENSE addon/LICENSE
grep -n "libraryPart" addon/Sources/ExtendedElementCommands.cpp | head -3   # patch drzwi obecny
grep -n 'CACHE STRING "" FORCE' addon/Tools/CMakeCommon.cmake | head -1        # patch CMake 4.x obecny
printf '\n# add-on C++ (build w $TMPDIR przez build_release.sh; lokalne buildy)\naddon/Build/\naddon/build/\n' >> .gitignore
```

`addon/NOTICE`:

```
FloorForge add-on = fork Tapir Archicad Automation (https://github.com/ENZYME-APD/tapir-archicad-automation),
licencja MIT (patrz LICENSE). Zmiany względem upstreamu v1.4.0:
- CreateDoors: parametry libraryPart / oSide / reflected (ExtendedElementCommands.cpp)
- Tools/CMakeCommon.cmake: `PARENT_SCOPE CACHE STRING` → `CACHE STRING` (CMake 4.x)
- tożsamość: MDID FloorForge, CFBundleIdentifier pl.d7studio.floorforge, nazwa FloorForge
- przestrzeń komend JSON: "FloorForgeCommand" (zamiast "TapirCommand")
- menu: FloorForge → Podział rzutu (uruchamia osadzony proces Pythona), O FloorForge…;
  paleta skryptów, Check for Updates i VersionChecker nie są rejestrowane
```

- [ ] **Step 2: Tożsamość — MDID, nazwa, identyfikator, wersja, przestrzeń komend**

`addon/Sources/RFIX/AddOnFix.grc` (linie 3-6):

```
'MDID' 32500 "Add-On Identifier" {
	879970669
	416370978
}
```

`addon/Sources/CommandBase.cpp:7`:

```cpp
constexpr const char* CommandNamespace = "FloorForgeCommand";
```

`addon/Sources/AddOnVersion.hpp` (cała treść):

```cpp
#pragma once

// Wersja wstrzykiwana przez CMake (-DFLOORFORGE_VERSION="v0.7-…"); fallback dla buildów ręcznych.
#ifndef FLOORFORGE_VERSION
#define FLOORFORGE_VERSION "dev"
#endif
#define ADDON_VERSION FLOORFORGE_VERSION
```

`addon/CMakeLists.txt` — zamień blok od `if (WIN32)` … `set (AddOnName …)` i dodaj definicję:

```cmake
set (AddOnName "FloorForge")
set (FLOORFORGE_VERSION "dev" CACHE STRING "Wersja FloorForge (git describe)")

project (${AddOnName})

set (AddOnSourcesFolder Sources)
set (AddOnResourcesFolder Sources)
GenerateAddOnProject (AddOn ${AC_VERSION} ${AC_API_DEVKIT_DIR} ${AddOnName} ${AddOnSourcesFolder} ${AddOnResourcesFolder} INT)
target_compile_definitions (AddOn PRIVATE FLOORFORGE_VERSION="${FLOORFORGE_VERSION}")
```

`addon/Tools/CMakeCommon.cmake` w `GenerateAddOnProject` (blok plist, ~linie 191-215):

```cmake
        set(MACOSX_BUNDLE_GUI_IDENTIFIER pl.d7studio.floorforge)
        set(MACOSX_BUNDLE_LONG_VERSION_STRING "FloorForge ${FLOORFORGE_VERSION}")
        set(MACOSX_BUNDLE_SHORT_VERSION_STRING ${FLOORFORGE_VERSION})
        set(MACOSX_BUNDLE_BUNDLE_VERSION ${FLOORFORGE_VERSION})
        set(MACOSX_BUNDLE_COPYRIGHT "Copyright © D7 Studio, 2026. Zawiera Tapir (MIT, Enzyme APD).")
```

oraz `XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER pl.d7studio.floorforge`. Zostaw resztę funkcji bez zmian.

- [ ] **Step 3: Zasoby menu i dialogu**

`addon/Sources/ResourceIds.hpp` — dodaj po `ID_ADDON_MENU_ABOUT`:

```cpp
#define ID_ADDON_MENU_LAUNCH            32002
#define ID_ADDON_MENU_LAUNCH_ITEM           1

#define ID_LAUNCHER_STRINGS             32012
#define ID_LAUNCHER_ALREADY_RUNNING_TITLE   1
#define ID_LAUNCHER_ALREADY_RUNNING_TEXT    2
#define ID_LAUNCHER_SPAWN_FAILED_TITLE      3
#define ID_LAUNCHER_SPAWN_FAILED_TEXT       4
#define ID_LAUNCHER_OK_BUTTON               5
```

(`32002` był `ID_ADDON_MENU_FOR_PALETTE` — usuń tamtą definicję i `ID_ADDON_MENU_FOR_UPDATE`; `ID_ADDON_MENU` 32001 zostaje dla „O FloorForge…".)

`addon/Sources/RINT/AddOn.grc` — zamień pierwsze cztery `STR#` na:

```
'STR#' ID_ADDON_INFO "Add-on Name and Description" {
/* [  1] */		"FloorForge"
/* [  2] */		"FloorForge — generator rzutów mieszkań i domów (CP-SAT) z zapisem do Archicada"
}

'STR#' ID_ADDON_MENU "Add-On Menu" {
/* [   ] */        "FloorForge"
/* [  1] */        "O FloorForge...^E3^ES^EE^EI^ED^EL^EW^ET^EM^32503"
}

'STR#' ID_ADDON_MENU_LAUNCH "Add-On Menu" {
/* [   ] */        "FloorForge"
/* [  1] */        "Podział rzutu^E3^ES^EE^EI^ED^EL^EW^ET^EM"
}

'STR#' ID_LAUNCHER_STRINGS "FloorForge Launcher Strings" {
/* [  1] */ "FloorForge"
/* [  2] */ "FloorForge jest już otwarty. Znajdź jego okno (Cmd+Tab)."
/* [  3] */ "FloorForge — błąd uruchomienia"
/* [  4] */ "Nie udało się uruchomić FloorForge z pliku:\n%T\n\nPrzeinstaluj FloorForge.bundle (skopiuj cały bundle do Dodatków)."
/* [  5] */ "OK"
}
```

Usuń `STR#` `ID_ADDON_MENU_FOR_PALETTE`, `ID_ADDON_MENU_FOR_UPDATE`, `ID_PALETTE_STRINGS`, `ID_AUTOUPDATE_STRINGS` oraz `GDLG`/`DLGH` `ID_PALETTE`. W `GDLG ID_ABOUT_DIALOG` zmień tytuł na `"FloorForge"`, tekst `[3]` na `"FloorForge — powłoka Archicad"`, `[4]` zostaje `"Version: %T, Port: %T"` → `"Wersja: %T, port JSON: %T"`.

- [ ] **Step 4: Launcher (nowy plik)**

`addon/Sources/FloorForgeLauncher.hpp`:

```cpp
#pragma once

namespace FloorForge {
// Uruchamia osadzony proces FloorForge (Contents/Resources/FloorForge/FloorForge) z env
// wskazującym port JSON tej instancji AC. Drugie wywołanie przy żyjącym procesie → alert.
void LaunchOrFocus ();
}
```

`addon/Sources/FloorForgeLauncher.cpp`:

```cpp
#include "FloorForgeLauncher.hpp"

#include "APIEnvir.h"
#include "ACAPinc.h"
#include "AddOnVersion.hpp"
#include "ResourceIds.hpp"

#include "Process.hpp"
#include "Location.hpp"
#include "UniString.hpp"

#include <cstdlib>
#include <string>

namespace FloorForge {

static GS::Process gProcess;   // ostatni uruchomiony proces (nieważny = nic nie uruchomiono)

static GS::UniString Str (short index)
{
    return RSGetIndString (ID_LAUNCHER_STRINGS, index, ACAPI_GetOwnResModule ());
}

// ACAPI_GetOwnLocation zwraca lokalizację bundla dodatku (…/FloorForge.bundle).
// Jeśli AC zwróci ścieżkę do binarki (…/Contents/MacOS/FloorForge), cofamy się o 3 poziomy.
static bool GetEmbeddedExecutablePath (GS::UniString& outPath)
{
    IO::Location loc;
    if (ACAPI_GetOwnLocation (&loc) != NoError) {
        return false;
    }
    IO::Name last;
    loc.GetLastLocalName (&last);
    if (last.ToString () == "FloorForge") {          // dostaliśmy binarkę, nie bundle
        loc.DeleteLastLocalName ();                   // MacOS
        loc.DeleteLastLocalName ();                   // Contents
        loc.DeleteLastLocalName ();                   // FloorForge.bundle → katalog nadrzędny? nie: zostajemy na bundlu
        loc.AppendToLocal (IO::Name ("FloorForge.bundle"));
    }
    loc.AppendToLocal (IO::Name ("Contents"));
    loc.AppendToLocal (IO::Name ("Resources"));
    loc.AppendToLocal (IO::Name ("FloorForge"));
    loc.AppendToLocal (IO::Name ("FloorForge"));
    loc.ToPath (&outPath);
    return true;
}

static bool IsRunning ()
{
    // WaitFor(0) zwraca true, gdy proces już się zakończył; false = nadal działa.
    return gProcess.IsValid () && !gProcess.WaitFor (static_cast<UInt32> (0));
}

void LaunchOrFocus ()
{
    if (IsRunning ()) {
        DGAlert (DG_INFORMATION, Str (ID_LAUNCHER_ALREADY_RUNNING_TITLE),
                 Str (ID_LAUNCHER_ALREADY_RUNNING_TEXT), GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
        return;
    }

    GS::UniString exePath;
    if (!GetEmbeddedExecutablePath (exePath)) {
        DGAlert (DG_ERROR, Str (ID_LAUNCHER_SPAWN_FAILED_TITLE),
                 GS::UniString::Printf (Str (ID_LAUNCHER_SPAWN_FAILED_TEXT), GS::UniString ("(ACAPI_GetOwnLocation)").ToPrintf ()),
                 GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
        return;
    }

    UShort port = 0;
    ACAPI_Command_GetHttpConnectionPort (&port);

    // Proces dziedziczy środowisko AC — ustawiamy zmienne przed spawnem (tylko FLOORFORGE_*).
    setenv ("FLOORFORGE_BETA", "1", 1);
    setenv ("FLOORFORGE_VERSION", ADDON_VERSION, 1);
    setenv ("FLOORFORGE_AC_PORT", std::to_string (port).c_str (), 1);
    setenv ("FLOORFORGE_LAUNCHED_FROM_AC", "1", 1);

    try {
        gProcess = GS::Process::Create (exePath, GS::Array<GS::UniString> (), GS::Process::CreateNoWindow);
    } catch (const GS::ProcessException&) {
        gProcess = GS::Process ();
    }
    if (!gProcess.IsValid ()) {
        DGAlert (DG_ERROR, Str (ID_LAUNCHER_SPAWN_FAILED_TITLE),
                 GS::UniString::Printf (Str (ID_LAUNCHER_SPAWN_FAILED_TEXT), exePath.ToPrintf ()),
                 GS::EmptyUniString, Str (ID_LAUNCHER_OK_BUTTON));
    }
}

} // namespace FloorForge
```

Uwagi dla implementera: (a) sprawdź w `IO::Location` (DevKit `Modules/InputOutput/Location.hpp`) dokładne nazwy metod `GetLastLocalName`/`DeleteLastLocalName`/`AppendToLocal` i popraw, jeśli różnią się; (b) semantykę `WaitFor(UInt32)` potwierdź w `Process.hpp` — jeśli zwraca odwrotnie, odwróć negację; (c) blok „dostaliśmy binarkę" jest asekuracją — w spike'u (Task 4) `ACAPI_WriteReport` ma wypisać `exePath`, a ta gałąź może zostać usunięta, jeśli AC zwraca bundle.

- [ ] **Step 5: `AddOnMain.cpp` — tylko menu FloorForge, bez palety i VersionCheckera**

W `addon/Sources/AddOnMain.cpp`: usuń `#include "TapirPalette.hpp"`, `#include "VersionChecker.hpp"`, dodaj `#include "FloorForgeLauncher.hpp"`. Zamień `MenuCommandHandler`, `CheckEnvironment`, `RegisterInterface` i początek `Initialize` na:

```cpp
static GSErrCode MenuCommandHandler (const API_MenuParams* menuParams)
{
    switch (menuParams->menuItemRef.menuResID) {
        case ID_ADDON_MENU:
            if (menuParams->menuItemRef.itemIndex == ID_ADDON_MENU_ABOUT) {
                AboutDialog aboutDialog;
                aboutDialog.Invoke ();
            }
            break;
        case ID_ADDON_MENU_LAUNCH:
            if (menuParams->menuItemRef.itemIndex == ID_ADDON_MENU_LAUNCH_ITEM) {
                FloorForge::LaunchOrFocus ();
            }
            break;
    }
    return NoError;
}

API_AddonType CheckEnvironment (API_EnvirParams* envir)
{
    RSGetIndString (&envir->addOnInfo.name, ID_ADDON_INFO, ID_ADDON_INFO_NAME, ACAPI_GetOwnResModule ());
    RSGetIndString (&envir->addOnInfo.description, ID_ADDON_INFO, ID_ADDON_INFO_DESC, ACAPI_GetOwnResModule ());
    envir->addOnInfo.description += GS::UniString (" ") + ADDON_VERSION;
    return APIAddon_Preload;
}

GSErrCode RegisterInterface (void)
{
    GSErrCode err = NoError;
    err |= ACAPI_MenuItem_RegisterMenu (ID_ADDON_MENU_LAUNCH, 0, MenuCode_UserDef, MenuFlag_Default);
    err |= ACAPI_MenuItem_RegisterMenu (ID_ADDON_MENU, 0, MenuCode_UserDef, MenuFlag_SeparatorBefore);
    return err;
}

GSErrCode Initialize (void)
{
    GSErrCode err = NoError;
    err |= ACAPI_MenuItem_InstallMenuHandler (ID_ADDON_MENU_LAUNCH, MenuCommandHandler);
    err |= ACAPI_MenuItem_InstallMenuHandler (ID_ADDON_MENU, MenuCommandHandler);
    // (dalej bez zmian: rejestracja grup komend JSON — RegisterCommand<…>)
```

Usuń wywołanie `TapirPalette::RegisterPaletteControlCallBack ()` i wszystkie odwołania do `TapirPalette`/`VersionChecker` w tym pliku. Pliki `TapirPalette.*`, `VersionChecker.*`, `UvManager.*` **usuń z `addon/Sources/`** (CMake globuje `Sources/*.cpp`; nieużywane źródła z `-Werror` i zależnością od zasobów palety psułyby build). Jeśli inny plik (np. `DeveloperTools.cpp`, `Config.cpp`) odwołuje się do palety — usuń tylko to odwołanie, zachowaj komendy.

- [ ] **Step 6: Build lokalny (RED→GREEN dla C++)**

```bash
cd "/Users/dawidcwiertniewicz/Desktop/claude code/FloorPlan6"
cmake -S addon -B addon/Build -DAC_VERSION=29 \
  -DAC_API_DEVKIT_DIR="/Users/dawidcwiertniewicz/Desktop/claude code/API archicad/Support" \
  -DFLOORFORGE_VERSION="dev-task1" 2>&1 | tail -5
cmake --build addon/Build --config RelWithDebInfo -j8 2>&1 | tail -15
ls addon/Build/RelWithDebInfo/FloorForge.bundle/Contents/MacOS/
plutil -p addon/Build/RelWithDebInfo/FloorForge.bundle/Contents/Info.plist | grep -E "CFBundleIdentifier|CFBundleShortVersionString|CFBundleName"
strings addon/Build/RelWithDebInfo/FloorForge.bundle/Contents/MacOS/FloorForge | grep -c FloorForgeCommand
```

Oczekiwane: build bez błędów, `Contents/MacOS/FloorForge`, identyfikator `pl.d7studio.floorforge`, wersja `dev-task1`, ≥1 wystąpienie `FloorForgeCommand`, 0 wystąpień `TapirCommand` (`strings … | grep -c TapirCommand` → 0). Błędy kompilacji z `-Werror` w nietkniętych plikach Tapira → najpierw sprawdź, czy tapir-custom buduje się tym samym poleceniem; różnice wynikają wtedy z usuniętych plików.

- [ ] **Step 7: Smoke załadowania w AC (ręczny, Dawid lub implementer z AC)**

Skopiuj `addon/Build/RelWithDebInfo/FloorForge.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`, **usuń stamtąd `TapirAddOn_AC29_Mac.bundle` i `FloorPlan4.bundle`** (ten sam MDID!), `codesign --force --sign - …/FloorForge.bundle`, uruchom AC. Oczekiwane: menu „FloorForge" z „Podział rzutu" i „O FloorForge…"; „O FloorForge…" pokazuje wersję `dev-task1` i port; „Podział rzutu" pokazuje alert o braku pliku (Python jeszcze nie osadzony) z pełną ścieżką `…/FloorForge.bundle/Contents/Resources/FloorForge/FloorForge` — to potwierdza `ACAPI_GetOwnLocation`. Zapisz obserwację w raporcie.

- [ ] **Step 8: Commit**

```bash
git add addon .gitignore
git commit -m "feat(addon): FloorForge.bundle — fork Tapira z tożsamością FloorForge i menu uruchamiającym osadzony proces

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 2: Python — przestrzeń komend, port z env, komunikat błędu

**Files:**
- Modify: `bridge/tapir_connection.py:28` (stała), `:90-125` (`connect()`), `notebooks/ac_story_switch_probe.py:22`, `notebooks/ac_story_diag.py:28`, `ui/user_errors.py` (gałąź ArchiCAD)
- Test: `tests/test_ac_port_env.py` (nowy), `tests/test_command_namespace.py` (nowy), `tests/test_user_errors.py` (rozszerzenie)

**Interfaces:**
- Produces: `TAPIR_NAMESPACE == "FloorForgeCommand"`; `TapirConnection.connect()` honoruje env `FLOORFORGE_AC_PORT` (int, 1..65535) → `use_port(port)`; niepoprawne/martwe → skan + `logger.warning`. `describe(ConnectionError)` przy `FLOORFORGE_LAUNCHED_FROM_AC=1` zwraca tekst z „Opcje → Ustawienia → JSON API".

- [ ] **Step 1: Failing tests**

```python
# tests/test_command_namespace.py
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_namespace_constant_is_floorforge():
    from bridge.tapir_connection import TAPIR_NAMESPACE
    assert TAPIR_NAMESPACE == "FloorForgeCommand"


def test_no_namespace_literal_outside_bridge():
    """Literał przestrzeni komend istnieje tylko w bridge/tapir_connection.py."""
    hits = []
    for p in list(ROOT.glob("*.py")) + list(ROOT.glob("ui/*.py")) + list(ROOT.glob("service/*.py")) \
            + list(ROOT.glob("notebooks/*.py")) + list(ROOT.glob("bridge/*.py")):
        if p.name.endswith(" 2.py"):
            continue
        if p == ROOT / "bridge" / "tapir_connection.py":
            continue
        if re.search(r'"(TapirCommand|FloorForgeCommand)"', p.read_text(encoding="utf-8")):
            hits.append(str(p.relative_to(ROOT)))
    assert hits == [], f"literał przestrzeni komend poza bridge: {hits}"


def test_addon_namespace_matches_python():
    src = (ROOT / "addon" / "Sources" / "CommandBase.cpp").read_text(encoding="utf-8")
    from bridge.tapir_connection import TAPIR_NAMESPACE
    assert f'CommandNamespace = "{TAPIR_NAMESPACE}"' in src
```

```python
# tests/test_ac_port_env.py
import pytest


def _conn(monkeypatch):
    import bridge.tapir_connection as tc
    tc.TapirConnection._instance = None          # świeży singleton
    c = tc.TapirConnection()
    calls = {"use_port": [], "scan": 0}
    monkeypatch.setattr(tc.TapirConnection, "_scan_for_archicad",
                        lambda self: (calls.__setitem__("scan", calls["scan"] + 1) or (19725, "scan-conn")))
    return tc, c, calls


def test_env_port_alive_is_used_without_scan(monkeypatch):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: "conn-19724" if port == 19724 else None))
    assert c.connect() is True
    assert c.active_port == 19724 and c._conn == "conn-19724"
    assert calls["scan"] == 0


def test_env_port_dead_falls_back_to_scan(monkeypatch, caplog):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert c.active_port == 19725 and calls["scan"] == 1
    assert any("FLOORFORGE_AC_PORT" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad", ["", "abc", "0", "70000"])
def test_env_port_invalid_falls_back_to_scan(monkeypatch, bad):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", bad)
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert calls["scan"] == 1


def test_no_env_keeps_scan_behaviour(monkeypatch):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert calls["scan"] == 1
```

Dopisz do `tests/test_user_errors.py`:

```python
def test_connection_error_when_launched_from_ac_mentions_json_api(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.setenv("FLOORFORGE_LAUNCHED_FROM_AC", "1")
    title, text = describe(ConnectionError("brak"))
    assert title == "ArchiCAD"
    assert "JSON API" in text and "Odśwież" in text


def test_connection_error_default_wording_without_env(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)
    _, text = describe(ConnectionError("brak"))
    assert "Uruchom AC" in text
```

Do autouse fixture `_isolated_env` w `tests/conftest.py` dodaj `monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)` i `monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)`.

- [ ] **Step 2: Run → FAIL**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_command_namespace.py tests/test_ac_port_env.py tests/test_user_errors.py -q -p no:cacheprovider
```

Oczekiwane: `test_namespace_constant_is_floorforge` FAIL (`"TapirCommand"`), `test_no_namespace_literal_outside_bridge` FAIL (2 notebooki), `test_addon_namespace_matches_python` PASS lub FAIL zależnie od Task 1, port-env testy FAIL (skan zamiast use_port), user_errors FAIL.

- [ ] **Step 3: Implementacja**

`bridge/tapir_connection.py:28`: `TAPIR_NAMESPACE = "FloorForgeCommand"`.

W `connect()` przed pętlą retry dodaj:

```python
        env_port = _env_ac_port()
        if env_port is not None:
            conn = self._try_connect(env_port)
            if conn is not None:
                self._active_port = env_port
                self._conn = conn
                logger.info("connect: port z FLOORFORGE_AC_PORT=%s", env_port)
                return True
            logger.warning("connect: FLOORFORGE_AC_PORT=%s nie odpowiada — skanuję porty", env_port)
```

i helper na poziomie modułu:

```python
def _env_ac_port() -> Optional[int]:
    """Port JSON instancji AC przekazany przez add-on (FLOORFORGE_AC_PORT). None gdy brak/niepoprawny."""
    raw = os.environ.get("FLOORFORGE_AC_PORT", "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        logger.warning("FLOORFORGE_AC_PORT niepoprawny: %r", raw)
        return None
    if not (1 <= port <= 65535):
        logger.warning("FLOORFORGE_AC_PORT poza zakresem: %s", port)
        return None
    return port
```

(`import os` na górze, jeśli brak.) Notebooki: `from bridge.tapir_connection import TAPIR_NAMESPACE as NS` zamiast `NS = "TapirCommand"` (oba mają już `sys.path.insert` do korzenia repo).

`ui/user_errors.py` — w gałęzi `ConnectionError` przed zwrotem:

```python
        if os.environ.get("FLOORFORGE_LAUNCHED_FROM_AC") == "1":
            return ("ArchiCAD",
                    "Uruchomiono z ArchiCADa, ale AC nie odpowiada na porcie JSON. "
                    "Sprawdź Opcje → Ustawienia → JSON API (port 19723) i kliknij Odśwież." + _tail(exc))
```

- [ ] **Step 4: Run → PASS + regresja**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_command_namespace.py tests/test_ac_port_env.py tests/test_user_errors.py tests/test_ac_targeting.py tests/test_house_export_gui.py tests/test_ac_status_widget.py tests/test_boundary_from_new_zone.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```bash
git add bridge/tapir_connection.py notebooks/ac_story_switch_probe.py notebooks/ac_story_diag.py ui/user_errors.py tests/conftest.py tests/test_command_namespace.py tests/test_ac_port_env.py tests/test_user_errors.py
git commit -m "feat(bridge): przestrzeń FloorForgeCommand + port AC z env FLOORFORGE_AC_PORT + komunikat przy starcie z AC

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 3: Pakowanie — bundle z osadzonym Pythonem, podpis, zip, bramka, smoke

**Files:**
- Modify: `packaging/floorforge.spec` (usunięcie `BUNDLE`), `packaging/build_release.sh` (przepisany), `packaging/smoke_frozen.sh` (ścieżka), `.gitignore`
- Delete: `packaging/Uruchom.command`, `packaging/make_icon.py`, `packaging/icon.icns`, `packaging/icon_1024.png` (jeśli jest)

**Interfaces:**
- Produces: `packaging/dist/FloorForge-<VER>.zip` rozpakowujący się do folderu `FloorForge-<VER>/FloorForge.bundle`; wewnątrz `Contents/MacOS/FloorForge` (add-on), `Contents/Resources/FloorForge/FloorForge` (Python, `--selftest` działa); `smoke_frozen.sh` → `SMOKE OK`.

- [ ] **Step 1: `floorforge.spec` — onedir bez `.app`**

Usuń blok `app = BUNDLE(...)`; `EXE(... console=False ...)` zostaje (bez `icon=`). `COLLECT(..., name="FloorForge")` zostaje. Dodaj komentarz: `# Produkt = katalog dist/FloorForge/ osadzany w FloorForge.bundle/Contents/Resources/FloorForge/ (build_release.sh)`.

- [ ] **Step 2: `build_release.sh` — przepisany**

```bash
#!/usr/bin/env bash
# packaging/build_release.sh — buduje FloorForge.bundle (add-on C++ + osadzony Python) i zip bety.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
exec > >(tee "$HERE/build.log") 2>&1

DEVKIT="${AC_API_DEVKIT_DIR:-/Users/dawidcwiertniewicz/Desktop/claude code/API archicad/Support}"
AC_VERSION="${AC_VERSION:-29}"

VER="${FLOORFORGE_VERSION:-}"
[ -n "$VER" ] || VER="$(cd "$ROOT" && git describe --tags --always --dirty)"
[ -n "$VER" ] || { echo "brak wersji: ustaw FLOORFORGE_VERSION"; exit 2; }
export FLOORFORGE_VERSION="$VER"
echo "== FloorForge $VER (AC$AC_VERSION)"
[ -f "$DEVKIT/Inc/ACAPinc.h" ] || { echo "BRAK DevKit: $DEVKIT/Inc/ACAPinc.h"; exit 2; }

VENV="$HERE/.venv"
if [ ! -x "$VENV/bin/python" ]; then python3.13 -m venv "$VENV" || python3 -m venv "$VENV"; fi
"$VENV/bin/python" -c 'import sys; assert sys.version_info[:2]==(3,13), sys.version' || { echo "venv buildera musi być Python 3.13"; exit 2; }
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$HERE/requirements-lock.txt"

# Praca poza katalogiem projektu (iCloud dokleja FinderInfo → codesign --strict pada).
WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-release.XXXXXX")"
keep_work() { local rc=$?; [ "$rc" -eq 0 ] || echo "== katalog roboczy ZOSTAJE do analizy: $WORK"; exit $rc; }
trap keep_work EXIT

# 1. Python (onedir)
rm -rf "$HERE/build"
(cd "$ROOT" && "$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$WORK/py" --workpath "$HERE/build" "$HERE/floorforge.spec")
[ -x "$WORK/py/FloorForge/FloorForge" ] || { echo "PyInstaller nie dał $WORK/py/FloorForge/FloorForge"; exit 1; }

# 2. Add-on C++
cmake -S "$ROOT/addon" -B "$WORK/addon-build" -DAC_VERSION="$AC_VERSION" -DAC_API_DEVKIT_DIR="$DEVKIT" -DFLOORFORGE_VERSION="$VER"
cmake --build "$WORK/addon-build" --config RelWithDebInfo -j8
BUNDLE="$WORK/addon-build/RelWithDebInfo/FloorForge.bundle"
[ -x "$BUNDLE/Contents/MacOS/FloorForge" ] || { echo "cmake nie dał $BUNDLE"; exit 1; }

# 3. Złożenie: Python do Resources/FloorForge
ditto "$WORK/py/FloorForge" "$BUNDLE/Contents/Resources/FloorForge"
[ -x "$BUNDLE/Contents/Resources/FloorForge/FloorForge" ] || { echo "brak osadzonego Pythona"; exit 1; }

# 4. Podpis ad-hoc całości (jak CLT install_to_archicad, plus --deep dla dylibów Pythona)
xattr -cr "$BUNDLE"
codesign --force --deep --sign - "$BUNDLE"
codesign --verify --deep --strict "$BUNDLE" || { echo "codesign FAIL"; exit 1; }
echo "codesign OK (ad-hoc)"

# 5. Zip
STAGE="$WORK/dist/FloorForge-$VER"; mkdir -p "$STAGE"
ditto "$BUNDLE" "$STAGE/FloorForge.bundle"
cp "$HERE/INSTALACJA.md" "$STAGE/"
ZIP="$WORK/dist/FloorForge-$VER.zip"
(cd "$WORK/dist" && ditto -c -k --keepParent --norsrc --noextattr "FloorForge-$VER" "FloorForge-$VER.zip")

# 6. Bramka — wyłącznie na tym, co pojedzie do testera
echo "== weryfikacja paczki"
AD="$(unzip -l "$ZIP" | grep -c '\._' || true)"; [ "$AD" -eq 0 ] || { echo "PACZKA FAIL: $AD plików AppleDouble"; exit 1; }
VERIFY="$WORK/verify"; mkdir -p "$VERIFY"; ditto -x -k "$ZIP" "$VERIFY"
VB="$VERIFY/FloorForge-$VER/FloorForge.bundle"
codesign --verify --deep --strict "$VB" || { echo "PACZKA FAIL: codesign z zipa"; exit 1; }
file "$VB/Contents/MacOS/FloorForge" | grep -q "Mach-O" || { echo "PACZKA FAIL: MacOS/FloorForge nie jest Mach-O"; exit 1; }
plutil -extract CFBundleIdentifier raw "$VB/Contents/Info.plist" | grep -qx "pl.d7studio.floorforge" || { echo "PACZKA FAIL: CFBundleIdentifier"; exit 1; }
VOUT="$("$VB/Contents/Resources/FloorForge/FloorForge" --selftest 2>&1 | tail -20 || true)"
echo "$VOUT"; echo "$VOUT" | grep -q "SELFTEST OK" || { echo "PACZKA FAIL: selftest z zipa"; exit 1; }
echo "bramka paczki OK"

# 7. dist — dopiero po bramce
mkdir -p "$HERE/dist"; rm -rf "$HERE"/dist/FloorForge-*
cp "$ZIP" "$HERE/dist/"; cp -R "$STAGE" "$HERE/dist/"
trap - EXIT; rm -rf "$WORK"
echo "== GOTOWE: $HERE/dist/FloorForge-$VER.zip"
```

- [ ] **Step 3: `smoke_frozen.sh`** — zmień wzorzec: `ZIP="$(ls -t "$HERE"/dist/FloorForge-*.zip …)"` i `BIN="$(find "$WORK" -type f -path '*/FloorForge.bundle/Contents/Resources/FloorForge/FloorForge' | head -1)"`, komunikat błędu „w paczce nie ma FloorForge.bundle/Contents/Resources/FloorForge/FloorForge". Reszta bez zmian.

- [ ] **Step 4: Usunięcia i `.gitignore`**

```bash
git rm -q packaging/Uruchom.command packaging/make_icon.py packaging/icon.icns
rm -f packaging/icon_1024.png
```

W `.gitignore` usuń wpisy `packaging/icon.iconset/`, `packaging/icon_1024.png` (zostaw `packaging/.venv/`, `packaging/build/`, `packaging/dist/`, `packaging/build.log`).

- [ ] **Step 5: Build + smoke**

```bash
chmod +x packaging/build_release.sh packaging/smoke_frozen.sh
packaging/build_release.sh 2>&1 | tail -20      # ~2-3 min (cmake + PyInstaller); w tle jeśli >10 min
packaging/smoke_frozen.sh
ls -la packaging/dist/
unzip -l packaging/dist/FloorForge-*.zip | grep -c '\._'
```

Oczekiwane: `== GOTOWE`, `SMOKE OK`, `0`. Rozmiar zipa ~85 MB. Jeśli `codesign --deep` odrzuca zagnieżdżone dyliby PyInstallera wewnątrz bundla add-onu (błąd „nested code"), podpisz najpierw `Contents/Resources/FloorForge` osobno (`codesign --force --deep --sign - "$BUNDLE/Contents/Resources/FloorForge"`), potem bundle bez `--deep`; opisz w raporcie.

- [ ] **Step 6: Commit**

```bash
git add packaging/floorforge.spec packaging/build_release.sh packaging/smoke_frozen.sh .gitignore
git commit -m "build(packaging): FloorForge.bundle z osadzonym Pythonem — cmake + PyInstaller + podpis + bramka z zipa

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 4: SPIKE kwarantanny (bramka live, Dawid) — pobrany bundle ładuje się i uruchamia okno

**Files:** brak zmian w kodzie (wynik → `docs/STATE.md` w Task 6). Ewentualna poprawka ścieżki w `addon/Sources/FloorForgeLauncher.cpp`, jeśli Step 7 z Task 1 pokazał, że `ACAPI_GetOwnLocation` zwraca coś innego.

**Interfaces:** rozstrzyga, czy proces Pythona uruchomiony przez AC z plików objętych kwarantanną startuje (spec §8, ryzyko #1).

- [ ] **Step 1 (Dawid, konto robocze):** `packaging/install_local.sh` jeszcze nie istnieje — zainstaluj ręcznie: skopiuj `packaging/dist/FloorForge-<VER>/FloorForge.bundle` do Dodatków (bez `TapirAddOn…` i `FloorPlan4.bundle`), `codesign --force --sign - "…/Dodatki/FloorForge.bundle"`, Cmd+Q, start AC, menu **FloorForge → Podział rzutu**. Oczekiwane: okno `FloorForge <VER>`, pasek AC pokazuje właściwy port i projekt **bez klikania Odśwież** (Task 2), M2 8×6 generuje i wstawia do AC.
- [ ] **Step 2 (Dawid, konto „beta-test"):** wgraj zip na iCloud Drive/Dysk Google, na koncie beta-test **pobierz go Safari** (to nadaje kwarantannę), sprawdź: `xattr -p com.apple.quarantine ~/Downloads/FloorForge-<VER>.zip` → wartość jest. Rozpakuj Finderem, `xattr -p com.apple.quarantine …/FloorForge-<VER>/FloorForge.bundle` → wartość jest (dziedziczona). Skopiuj bundle do Dodatków, start AC, menu → **Podział rzutu**.
- [ ] **Step 3: Wynik.** (a) menu widoczne + okno startuje → **PASS**, zapisz w STATE (Task 6). (b) AC nie ładuje bundla („nie może potwierdzić poprawności dodatku" lub brak menu) → FAIL na poziomie add-onu — porównaj z CLT na tym samym koncie (jeśli CLT też nie ładuje, problem jest w kwarantannie bundla, nie w FloorForge). (c) menu jest, ale okno nie startuje → FAIL na poziomie procesu Pythona: `Console.app` filtr `FloorForge` lub `log show --last 5m --predicate 'process == "FloorForge" OR eventMessage CONTAINS "FloorForge"'`, plus `~/Library/Logs/FloorForge/floorforge.log`. Przy (b)/(c) **STOP** — decyzja Dawida wg spec §8 (notaryzacja / zdejmowanie kwarantanny przez add-on / `xattr` w instrukcji).

---

### Task 5: `install_local.sh`, INSTALACJA, CHECKLIST

**Files:**
- Create: `packaging/install_local.sh`
- Modify: `packaging/INSTALACJA.md` (przepisany), `packaging/CHECKLIST_TEST.md` (przepisany)

**Interfaces:**
- Produces: `install_local.sh [ścieżka.zip|ścieżka.bundle]` — domyślnie najnowszy zip z `packaging/dist`; instaluje do `/Applications/Graphisoft/Archicad 29/Dodatki/FloorForge.bundle`, usuwa kolizje, podpisuje ad-hoc, przypomina o restarcie AC.

- [ ] **Step 1: `install_local.sh`**

```bash
#!/usr/bin/env bash
# packaging/install_local.sh — instaluje FloorForge.bundle do Dodatków AC29 (wzór: clt-panels/tools/install.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDONS="${ARCHICAD_ADDON_DIR:-/Applications/Graphisoft/Archicad 29/Dodatki}"
SRC="${1:-}"
[ -d "$ADDONS" ] || { echo "Brak katalogu Dodatków: $ADDONS"; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-install.XXXXXX")"; trap 'rm -rf "$WORK"' EXIT
if [ -z "$SRC" ]; then
  SRC="$(ls -t "$HERE"/dist/FloorForge-*.zip 2>/dev/null | head -1 || true)"
  [ -n "$SRC" ] || { echo "Brak paczki w $HERE/dist — uruchom build_release.sh"; exit 2; }
fi
case "$SRC" in
  *.zip)    ditto -x -k "$SRC" "$WORK"; BUNDLE="$(find "$WORK" -type d -name FloorForge.bundle | head -1)";;
  *.bundle) BUNDLE="$SRC";;
  *) echo "Podaj .zip albo .bundle"; exit 2;;
esac
[ -x "$BUNDLE/Contents/MacOS/FloorForge" ] || { echo "To nie jest FloorForge.bundle: $BUNDLE"; exit 1; }

# Kolizje: ten sam MDID (FloorPlan4) i te same komendy JSON (stary Tapir) = niezdefiniowane zachowanie AC.
for old in "FloorPlan4.bundle" "TapirAddOn_AC29_Mac.bundle" "FloorForge.bundle"; do
  if [ -e "$ADDONS/$old" ]; then echo "usuwam $ADDONS/$old"; rm -rf "$ADDONS/$old"; fi
done
ditto "$BUNDLE" "$ADDONS/FloorForge.bundle"
codesign --force --deep --sign - "$ADDONS/FloorForge.bundle"
codesign --verify --deep --strict "$ADDONS/FloorForge.bundle" && echo "codesign OK"
echo "Zainstalowano $ADDONS/FloorForge.bundle (wersja: $(plutil -extract CFBundleShortVersionString raw "$ADDONS/FloorForge.bundle/Contents/Info.plist"))."
echo "Zamknij Archicad (Cmd+Q) i uruchom ponownie."
```

- [ ] **Step 2: `INSTALACJA.md` (cała treść)**

```markdown
# FloorForge — instalacja (macOS, Archicad 29)

1. Zamknij Archicad (Cmd+Q).
2. Skopiuj `FloorForge.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`.
   Jeśli masz tam `TapirAddOn_AC29_Mac.bundle` albo `FloorPlan4.bundle` — usuń je (FloorForge je zastępuje).
3. Uruchom Archicad. W pasku menu pojawi się **FloorForge → Podział rzutu**.

Gdy coś nie działa: **FloorForge → O FloorForge…** pokazuje wersję i port; log aplikacji jest w
`~/Library/Logs/FloorForge/floorforge.log` — prześlij go razem ze zrzutem ekranu.
```

- [ ] **Step 3: `CHECKLIST_TEST.md` (przepisany)** — nagłówek jak dziś (konto „beta-test", brak Pythona/repo, jest AC29), krok 0 = wynik spike'u z Task 4 (PASS/FAIL, data), tabela:

```markdown
| # | Krok | Oczekiwane | OK? |
|---|---|---|---|
| 1 | Pobierz zip Safari na konto beta-test, rozpakuj Finderem | folder `FloorForge-<wersja>/` z `FloorForge.bundle` i `INSTALACJA.md`, bez plików `._*` | |
| 2 | Wykonaj `INSTALACJA.md` (kopia bundla, start AC) | AC startuje bez komunikatów o dodatku; w menu jest „FloorForge" | |
| 3 | **FloorForge → O FloorForge…** | wersja = `<wersja>` z nazwy zipa, port JSON (np. 19723) | |
| 4 | **FloorForge → Podział rzutu** (bez otwartego projektu) | okno `FloorForge <wersja>`, jedna zakładka „Podział rzutu", pasek `AC port … · (nieznany) · kondygnacja …` **bez klikania Odśwież** | |
| 5 | Drugi raz **Podział rzutu** przy otwartym oknie | alert „FloorForge jest już otwarty", drugie okno NIE powstaje | |
| 6 | Otwórz projekt testowy w AC → **Odśwież** w FloorForge | `AC port <ten sam> · <nazwa projektu> · kondygnacja Parter` | |
| 7 | Mieszkanie: zaznacz ściany obrysu M3 → „Wczytaj obrys z ArchiCAD" | podgląd obrysu, typ M3 | |
| 8 | „3. Generuj układy" | ≥ 1 wariant, < 30 s | |
| 9 | „Wstaw do ArchiCAD" | strefy, ściany, drzwi, okna, etykiety w AC | |
| 10 | Dom 10×8 ręcznie, tryb Dom → „3. Generuj układy" | parter + poddasze, ≤ 2 min | |
| 11 | „Wstaw obie kondygnacje (auto-przełączanie w AC)" → Wstaw | parter na story 0, poddasze na story 1, ten sam projekt; **FAIL** gdy obie na jednej story bez ostrzeżenia | |
| 12 | Zamknij okno FloorForge, zamknij AC (Cmd+Q), uruchom AC → Podział rzutu | okno startuje ponownie (proces nie „wisi" po zamknięciu AC) | |
| 13 | Wyłącz AC przy otwartym oknie FloorForge → „Wstaw do ArchiCAD" | dialog „ArchiCAD: Uruchomiono z ArchiCADa, ale AC nie odpowiada…" ze ścieżką logu, bez crasha | |
| 14 | Otwórz `~/Library/Logs/FloorForge/floorforge.log` | wpisy INFO (`connect: port z FLOORFORGE_AC_PORT=…`) + traceback z kroku 13 | |
```

Sekcja „Wynik": 14/14 OK → tag `v0.7-beta1` → FF do `main` → wysyłka zipa 2–3 osobom („przy błędzie prześlij log + zrzut"). Dowolny FAIL → STATE, poprawka, rebuild, od kroku 1.

- [ ] **Step 4: Instalacja lokalna + commit**

```bash
chmod +x packaging/install_local.sh && packaging/install_local.sh   # na koncie roboczym Dawida
git add packaging/install_local.sh packaging/INSTALACJA.md packaging/CHECKLIST_TEST.md
git commit -m "build(packaging): install_local.sh + INSTALACJA i CHECKLIST pod FloorForge.bundle

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
```

---

### Task 6: README, STATE, pełna suita, push

**Files:**
- Modify: `README.md` (sekcja „Beta (macOS + ArchiCAD 29)"), `docs/STATE.md` (nowy wpis NEXT SESSION na górze), `docs/superpowers/specs/2026-09-14-beta-dystrybucja-macos-design.md` (nota na górze: „forma dystrybucji zastąpiona przez spec 2026-09-15")

- [ ] **Step 1: README** — sekcja „Beta" opisuje: `packaging/build_release.sh` → `packaging/dist/FloorForge-<ver>.zip` (jeden `FloorForge.bundle`: add-on C++ z `addon/` + osadzony Python), instalacja = kopia do Dodatków, `packaging/install_local.sh`, `packaging/smoke_frozen.sh`, spec 2026-09-15. Usuń zdania o `.app`, `Uruchom.command`, `FLOORFORGE_BETA` jako ręcznej fladze (zostaje jako mechanizm).
- [ ] **Step 2: STATE.md** — wpis: co dostarczono (Task 1–5 z SHA), wynik spike'u (Task 4) i `ACAPI_GetOwnLocation` (bundle czy binarka), znane luki (paleta/VersionChecker usunięte z bundla; `FloorPlan4.bundle` i stary Tapir niekompatybilne z FloorForge w Dodatkach; kwarantanna: wynik), bramka: `CHECKLIST_TEST.md` 14/14 → tag `v0.7-beta1`.
- [ ] **Step 3: Pełna suita (raz)**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -3
```

Oczekiwane: `0 failed` poza znanym flaky CP-SAT (`test_house_service_placement…` — powtórz w izolacji).

- [ ] **Step 4: Commit + push gałęzi**

```bash
git add README.md docs/STATE.md docs/superpowers/specs/2026-09-14-beta-dystrybucja-macos-design.md
git commit -m "docs: FloorForge.bundle — README/STATE, nota o zastąpieniu specu 09-14

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X4TGNb4fg6SpWaoN2pXyL8"
git push origin feat/beta-macos
```

- [ ] **Step 5: BRAMKA (Dawid):** `packaging/CHECKLIST_TEST.md` na koncie beta-test → 14/14 → tag `v0.7-beta1`, FF `main`, push, wysyłka.

---

## Self-Review

**Spec coverage:** §1 zakres → T1 (addon), T2 (Python), T3 (build), T5 (INSTALACJA/CHECKLIST) ✓. §2 układ bundla + tożsamość + brak menu Tapira → T1 Step 2/3/5, T3 Step 2 (Resources/FloorForge) ✓. §3 launcher (ścieżka, env z portem, spawn `GS::Process`, „już otwarty", alert) → T1 Step 4 ✓. §4 Python (stała, `FLOORFORGE_AC_PORT`, notebooki, komunikat) → T2 ✓; „AcStatusWidget preferuje port z env" — pokryte pośrednio: `connect()` łączy z tym portem, a widget listuje instancje; brak osobnej zmiany w widgecie (YAGNI; checklist krok 4/6 to weryfikuje). §5 build 1–8 → T3 (1–7) + T5 (`install_local.sh` = 8) ✓. §6 testy → T2 (pytest), T1 Step 6 (C++ build), T3 Step 5 (smoke), T4 (spike), T5 Step 3 (checklist) ✓. §7 kolejność: spike jest T4 (po zbudowaniu bundla, bo bez bundla nie ma czego pobrać) — spec mówił „krok 0 na minimalnym bundlu"; minimalny bundle = T1–T3, więc kolejność zachowana w duchu. §8 ryzyka → T4 Step 3, T5 Step 1 (kolizje MDID), `addon/NOTICE` ✓.

**Placeholder scan:** brak TBD. Kod C++ w T1 zawiera jawne uwagi o nazwach metod `IO::Location`/`WaitFor` do potwierdzenia w DevKit — to instrukcja weryfikacji, nie placeholder.

**Type consistency:** `TAPIR_NAMESPACE` (T2) = test w `test_command_namespace.py` czyta `addon/Sources/CommandBase.cpp` (T1) ✓. Env `FLOORFORGE_AC_PORT` ustawiane w T1 (`setenv`) = czytane w T2 (`_env_ac_port`) ✓. Ścieżka `Contents/Resources/FloorForge/FloorForge` w T1 (launcher) = T3 (`ditto` + bramka) = `smoke_frozen.sh` = T5 (`install_local.sh` sprawdza `Contents/MacOS/FloorForge`) ✓. `FLOORFORGE_VERSION` CMake → `ADDON_VERSION` → env → tytuł okna (istniejące `is_beta()`/tytuł) ✓.
