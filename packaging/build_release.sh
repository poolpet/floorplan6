#!/usr/bin/env bash
# packaging/build_release.sh — buduje FloorForge.app + zip bety (macOS, ad-hoc sign).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TAPIR_BUNDLE="$ROOT/../tapir-custom/archicad-addon/Build/RelWithDebInfo/TapirAddOn_AC29_Mac.bundle"
export FLOORFORGE_VERSION="${FLOORFORGE_VERSION:-$(cd "$ROOT" && git describe --tags --always --dirty)}"

echo "== FloorForge beta $FLOORFORGE_VERSION"
[ -d "$TAPIR_BUNDLE" ] || { echo "BRAK bundla Tapira: $TAPIR_BUNDLE — zbuduj tapir-custom (cmake) najpierw"; exit 2; }

VENV="$HERE/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3.13 -m venv "$VENV" || python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$HERE/requirements-lock.txt"

# Ikona jest w repo; regenerujemy tylko gdy jej brak (matplotlib jest w locku).
[ -f "$HERE/icon.icns" ] || "$VENV/bin/python" "$HERE/make_icon.py"

# .app powstaje POZA katalogiem projektu. Powód: katalog projektu leży pod file
# providerem (iCloud „Biurko i Dokumenty"), który w ~3 s po utworzeniu dokleja
# com.apple.FinderInfo do każdego katalogu-bundla (*.framework, *.app), a wtedy
# `codesign --verify --strict` odmawia: "resource fork, Finder information, or
# similar detritus not allowed". Czyszczenie xattr na miejscu przegrywa wyścig
# z providerem — dlatego podpisujemy i pakujemy w $TMPDIR, a do packaging/dist
# wracają gotowe artefakty.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-release.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

rm -rf "$HERE/build" "$HERE/dist"
mkdir -p "$HERE/dist"
(cd "$ROOT" && "$VENV/bin/pyinstaller" --noconfirm --clean --distpath "$WORK/dist" --workpath "$HERE/build" "$HERE/floorforge.spec")

APP="$WORK/dist/FloorForge.app"
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
if ! codesign --verify --deep --strict "$APP"; then
  echo "codesign FAIL — podpis nie przeszedł weryfikacji"; exit 1
fi
echo "codesign OK (ad-hoc)"

STAGE="$WORK/dist/FloorForge-beta-$FLOORFORGE_VERSION"
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
cp -R "$TAPIR_BUNDLE" "$STAGE/"
cp "$HERE/INSTALACJA.md" "$HERE/Uruchom.command" "$STAGE/"
chmod +x "$STAGE/Uruchom.command"
# Wersja dla Uruchom.command: LSEnvironment z Info.plist działa tylko przy starcie
# z Findera, a binarka odpalona z shella dziedziczy środowisko terminala.
printf '%s\n' "$FLOORFORGE_VERSION" > "$STAGE/VERSION"
(cd "$WORK/dist" && ditto -c -k --keepParent "FloorForge-beta-$FLOORFORGE_VERSION" "FloorForge-beta-$FLOORFORGE_VERSION.zip")

# Artefakty do repo: zip (produkt) + .app i staging (smoke, ręczne odpalenie GUI).
cp "$WORK/dist/FloorForge-beta-$FLOORFORGE_VERSION.zip" "$HERE/dist/"
cp -R "$APP" "$HERE/dist/"
cp -R "$STAGE" "$HERE/dist/"
echo "== GOTOWE: $HERE/dist/FloorForge-beta-$FLOORFORGE_VERSION.zip"
