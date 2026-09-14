#!/usr/bin/env bash
# packaging/build_release.sh — buduje FloorForge.app + zip bety (macOS, ad-hoc sign).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Cały przebieg leci też do build.log (gitignorowany) — żeby nie trzeba było
# pamiętać o przekierowaniu przy ręcznym uruchomieniu.
exec > >(tee "$HERE/build.log") 2>&1

TAPIR_BUNDLE="$ROOT/../tapir-custom/archicad-addon/Build/RelWithDebInfo/TapirAddOn_AC29_Mac.bundle"

# Wersja osobno: `export X="${X:-$(...)}"` schowałby błąd git describe przed errexit.
VER="${FLOORFORGE_VERSION:-}"
if [ -z "$VER" ]; then
  VER="$(cd "$ROOT" && git describe --tags --always --dirty)"
fi
[ -n "$VER" ] || { echo "brak wersji: git describe nic nie zwrócił, ustaw FLOORFORGE_VERSION"; exit 2; }
export FLOORFORGE_VERSION="$VER"

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
# z providerem — dlatego podpisujemy, pakujemy i WERYFIKUJEMY w $TMPDIR, a do
# packaging/dist wracają dopiero sprawdzone artefakty.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-release.XXXXXX")"
# Katalog roboczy znika TYLKO po pełnym sukcesie (patrz koniec skryptu). Przy
# porażce bramki zostaje na dysku — inaczej nie ma czego obejrzeć po fakcie.
keep_work() {
  rc=$?
  [ "$rc" -eq 0 ] || echo "== katalog roboczy ZOSTAJE do analizy: $WORK"
  exit $rc
}
trap keep_work EXIT

# `packaging/dist` NIE jest tu kasowany: nieudany build nie może zniszczyć
# ostatniej dobrej paczki. Stare artefakty lecą dopiero po przejściu bramki.
rm -rf "$HERE/build"
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
ZIP="$WORK/dist/FloorForge-beta-$FLOORFORGE_VERSION.zip"
# --norsrc/--noextattr: bez nich ditto wkłada do zipa pliki AppleDouble (`._*`)
# z xattr, które tester widzi po rozpakowaniu byle czym innym niż Finder.
(cd "$WORK/dist" && ditto -c -k --keepParent --norsrc --noextattr "FloorForge-beta-$FLOORFORGE_VERSION" "FloorForge-beta-$FLOORFORGE_VERSION.zip")

# BRAMKA: sprawdzamy dokładnie to, co pojedzie do testera — .app rozpakowany
# z zipa, nie oryginał z dist. Obie kontrole są fatalne.
echo "== weryfikacja paczki"
AD="$(unzip -l "$ZIP" | grep -c '/\._' || true)"
if [ "$AD" -ne 0 ]; then
  echo "PACZKA FAIL: w zipie jest $AD plików AppleDouble (._*)"; exit 1
fi
echo "AppleDouble w zipie: 0 OK"
VERIFY="$WORK/verify"
mkdir -p "$VERIFY"
ditto -x -k "$ZIP" "$VERIFY"
VAPP="$VERIFY/FloorForge-beta-$FLOORFORGE_VERSION/FloorForge.app"
if ! codesign --verify --deep --strict "$VAPP"; then
  echo "PACZKA FAIL: .app z zipa nie przechodzi codesign --verify --deep --strict"; exit 1
fi
echo "codesign z paczki OK"
VOUT="$("$VAPP/Contents/MacOS/FloorForge" --selftest 2>&1 | tail -20 || true)"
echo "$VOUT"
echo "$VOUT" | grep -q "SELFTEST OK" || { echo "PACZKA FAIL: selftest z zipa nie przeszedł"; exit 1; }
echo "selftest z paczki OK"

# Bramka przeszła — DOPIERO TERAZ ruszamy packaging/dist. Do repo trafia zip
# (produkt) + staging (podglądowa, uruchamialna kopia). Gołego .appa NIE
# kopiujemy: file provider i tak by go ostemplował, a to drugie 200 MB tego samego.
rm -rf "$HERE"/dist/FloorForge-beta-*
cp "$ZIP" "$HERE/dist/"
cp -R "$STAGE" "$HERE/dist/"

# Sukces — dopiero tu wolno skasować katalog roboczy.
trap - EXIT
rm -rf "$WORK"
echo "== GOTOWE: $HERE/dist/FloorForge-beta-$FLOORFORGE_VERSION.zip"
