#!/usr/bin/env bash
# packaging/install_local.sh — instaluje FloorForge.bundle do Dodatków AC29 (wzór: clt-panels/tools/install.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ADDONS="${ARCHICAD_ADDON_DIR:-/Applications/Graphisoft/Archicad 29/Dodatki}"
# Kopie starych dodatków trzymamy POZA Dodatkami: Archicad skanuje podfoldery Dodatków,
# także ukryte (kropko-katalogi), i ładował z backupu drugą kopię FloorForge/FloorPlan4/Tapira.
BACKUP_ROOT="${FLOORFORGE_BACKUP_DIR:-$HOME/Library/Application Support/FloorForge/backups}"
SRC="${1:-}"

[ "$(uname -m)" = "arm64" ] || echo "UWAGA: Ten Mac nie jest Apple Silicon — osadzony FloorForge nie uruchomi się."
[ -d "$ADDONS" ] || { echo "Brak katalogu Dodatków: $ADDONS"; exit 2; }

# Nowy bundle składamy obok celu (.FloorForge.new) i podmieniamy dopiero po udanym podpisie —
# nieudana kopia/podpis nigdy nie zostawia Dodatków bez działającego dodatku. Katalog roboczy
# sprząta trap EXIT — Archicad startuje dopiero po instalacji, więc nigdy go nie widzi.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-install.XXXXXX")"
NEW="$ADDONS/.FloorForge.new"
trap 'rm -rf "$WORK" "$NEW"' EXIT

if [ -z "$SRC" ]; then
  SRC="$(ls -t "$HERE"/dist/FloorForge-*.zip 2>/dev/null | head -1 || true)"
  [ -n "$SRC" ] || { echo "Brak paczki w $HERE/dist — uruchom build_release.sh"; exit 2; }
fi
SRC="${SRC%/}"
case "$SRC" in
  *.zip)    ditto -x -k "$SRC" "$WORK"; BUNDLE="$(find "$WORK" -type d -name FloorForge.bundle | head -1)";;
  *.bundle) BUNDLE="$SRC";;
  *) echo "Podaj .zip albo .bundle"; exit 2;;
esac
[ -x "$BUNDLE/Contents/MacOS/FloorForge" ] || { echo "To nie jest FloorForge.bundle: $BUNDLE"; exit 1; }

TARGET="$ADDONS/FloorForge.bundle"
SRC_REAL="$(cd "$(dirname "$BUNDLE")" && pwd -P)/$(basename "$BUNDLE")"
TARGET_REAL="$(cd "$ADDONS" && pwd -P)/FloorForge.bundle"
if [ "$SRC_REAL" = "$TARGET_REAL" ]; then
  echo "Źródło jest już zainstalowanym dodatkiem: $TARGET_REAL"
  echo "Podaj zip albo bundle spoza Dodatków (instalacja z samego siebie skasowałaby źródło)."
  exit 2
fi

# 1. Złóż i podpisz kopię obok celu. --norsrc --noextattr: FinderInfo/resource forks to "detritus"
#    dla codesign --verify --strict.
rm -rf "$NEW"
ditto --norsrc --noextattr "$BUNDLE" "$NEW"
codesign --force --deep --sign - "$NEW"
codesign --verify --deep --strict "$NEW" || { echo "codesign FAIL — instalacja przerwana"; exit 1; }
echo "codesign OK"

# 2. Kolizje do backupu: ten sam MDID (FloorPlan4) i te same komendy JSON (stary Tapir) = niezdefiniowane
#    zachowanie AC. Przenosimy, nie kasujemy — żeby dało się wrócić. Katalog backupu powstaje
#    dopiero gdy jest co przenieść.
BACKUP="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"
BACKED_UP=0
for old in "FloorPlan4.bundle" "TapirAddOn_AC29_Mac.bundle" "FloorForge.bundle"; do
  if [ -e "$ADDONS/$old" ]; then
    mkdir -p "$BACKUP"
    echo "przenoszę $old do $BACKUP/"
    mv "$ADDONS/$old" "$BACKUP/"
    BACKED_UP=1
  fi
done

# 2b. Sprzątanie po starszej wersji instalatora, która odkładała kopie DO Dodatków —
#     Archicad ładował je jako drugi komplet dodatków. Wynosimy je na zewnątrz.
for stale in "$ADDONS"/.floorforge-backup-*; do
  [ -e "$stale" ] || continue
  mkdir -p "$BACKUP"
  echo "wynoszę stary backup $(basename "$stale") z Dodatków do $BACKUP/"
  mv "$stale" "$BACKUP/"
  BACKED_UP=1
done

# 3. Podmiana — ostatni krok, już po udanym podpisie.
mv "$NEW" "$TARGET"
VER="$(plutil -extract CFBundleShortVersionString raw "$TARGET/Contents/Info.plist" 2>/dev/null || echo "?")"
echo "Zainstalowano $TARGET (wersja: $VER)."
if [ "$BACKED_UP" -eq 1 ]; then
  echo "Kopie starych dodatków: $BACKUP — można usunąć, gdy FloorForge działa."
fi
echo "Zamknij Archicad (Cmd+Q) i uruchom ponownie."
