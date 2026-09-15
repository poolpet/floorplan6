#!/usr/bin/env bash
# packaging/install_local.sh — instaluje FloorForge.bundle do Dodatków AC29 (wzór: clt-panels/tools/install.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDONS="${ARCHICAD_ADDON_DIR:-/Applications/Graphisoft/Archicad 29/Dodatki}"
SRC="${1:-}"
[ -d "$ADDONS" ] || { echo "Brak katalogu Dodatków: $ADDONS"; exit 2; }

[ "$(uname -m)" = "arm64" ] || echo "UWAGA: Ten Mac nie jest Apple Silicon — osadzony FloorForge nie uruchomi się."

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
# --norsrc --noextattr: FinderInfo/resource forks = "detritus" dla codesign --verify --strict
# (bundle rozpakowany z zipa jest czysty, ale ten z dist/ niesie xattr po cp -R).
ditto --norsrc --noextattr "$BUNDLE" "$ADDONS/FloorForge.bundle"
codesign --force --deep --sign - "$ADDONS/FloorForge.bundle"
codesign --verify --deep --strict "$ADDONS/FloorForge.bundle" && echo "codesign OK"
echo "Zainstalowano $ADDONS/FloorForge.bundle (wersja: $(plutil -extract CFBundleShortVersionString raw "$ADDONS/FloorForge.bundle/Contents/Info.plist"))."
echo "Zamknij Archicad (Cmd+Q) i uruchom ponownie."
