#!/usr/bin/env bash
# packaging/build_release.sh — buduje FloorForge.bundle (add-on C++ + osadzony Python) i zip bety.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
exec > >(tee "$HERE/build.log") 2>&1

DEVKIT="${AC_API_DEVKIT_DIR:-/Users/dawidcwiertniewicz/Desktop/claude code/API archicad/Support}"
AC_VERSION="${AC_VERSION:-29}"

# Wersja osobno: `export X="${X:-$(...)}"` schowałby błąd git describe przed errexit.
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
# Katalog roboczy znika TYLKO po pełnym sukcesie — przy porażce bramki zostaje na
# dysku, inaczej nie ma czego obejrzeć po fakcie.
keep_work() { local rc=$?; [ "$rc" -eq 0 ] || echo "== katalog roboczy ZOSTAJE do analizy: $WORK"; exit $rc; }
trap keep_work EXIT

# 1. Python (onedir)
rm -rf "$HERE/build"
(cd "$ROOT" && "$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$WORK/py" --workpath "$HERE/build" "$HERE/floorforge.spec")
[ -x "$WORK/py/FloorForge/FloorForge" ] || { echo "PyInstaller nie dał $WORK/py/FloorForge/FloorForge"; exit 1; }

# 2. Add-on C++
# -DCMAKE_BUILD_TYPE jest KONIECZNE: generator Makefiles ignoruje `--config` i bez
# tego bundle ląduje w "$WORK/addon-build/FloorForge.bundle", nie w RelWithDebInfo/.
# Generatora Xcode nie używamy — jego faza CodeSign pada na dysku pod iCloudem.
cmake -S "$ROOT/addon" -B "$WORK/addon-build" -DAC_VERSION="$AC_VERSION" -DAC_API_DEVKIT_DIR="$DEVKIT" -DFLOORFORGE_VERSION="$VER" -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$WORK/addon-build" --config RelWithDebInfo -j8
BUNDLE="$WORK/addon-build/RelWithDebInfo/FloorForge.bundle"
[ -x "$BUNDLE/Contents/MacOS/FloorForge" ] || { echo "cmake nie dał $BUNDLE"; exit 1; }

# 3. Złożenie: Python do Resources/FloorForge
ditto "$WORK/py/FloorForge" "$BUNDLE/Contents/Resources/FloorForge"
[ -x "$BUNDLE/Contents/Resources/FloorForge/FloorForge" ] || { echo "brak osadzonego Pythona"; exit 1; }

# 4. Podpis ad-hoc całości (jak CLT install_to_archicad, plus --deep dla dylibów Pythona)
# chmod PRZED xattr: cmake zostawia Contents/PkgInfo z prawami 444, a `xattr -cr`
# wywala się wtedy na EPERM i przy errexit ubija cały build.
chmod -R u+w "$BUNDLE"
xattr -cr "$BUNDLE"
# `--deep` podpisuje też Mach-O zaszyte w Resources/FloorForge (exe PyInstallera,
# Python.framework, 12 frameworków Qt, ~200 dylibów) — osobne podpisywanie nie jest
# potrzebne, sprawdzone `--verify --deep --strict` niżej.
codesign --force --deep --sign - "$BUNDLE"
codesign --verify --deep --strict "$BUNDLE" || { echo "codesign FAIL"; exit 1; }
echo "codesign OK (ad-hoc)"

# 5. Zip
STAGE="$WORK/dist/FloorForge-$VER"; mkdir -p "$STAGE"
ditto "$BUNDLE" "$STAGE/FloorForge.bundle"
cp "$HERE/INSTALACJA.md" "$STAGE/"
ZIP="$WORK/dist/FloorForge-$VER.zip"
# --norsrc/--noextattr: bez nich ditto wkłada do zipa pliki AppleDouble (`._*`),
# które tester widzi po rozpakowaniu czymkolwiek innym niż Finder.
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
