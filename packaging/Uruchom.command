#!/usr/bin/env bash
# Uruchom.command — awaryjne uruchomienie FloorForge z widocznym terminalem.
# Binarka odpalona z shella nie dostaje LSEnvironment z Info.plist, więc tryb bety
# i wersję (plik VERSION leżący obok .app) ustawiamy tutaj.
DIR="$(cd "$(dirname "$0")" && pwd)"   # liczymy PRZED cd — $0 bywa ścieżką względną
cd "$DIR"
export FLOORFORGE_BETA=1
VER="$(cat "$DIR/VERSION" 2>/dev/null || true)"
export FLOORFORGE_VERSION="${VER:-beta}"

# Najpierw obok tego pliku (tak wygląda rozpakowana paczka), potem typowe miejsca,
# gdyby ktoś jednak przeniósł sam .app do Programów.
for APP in "$DIR/FloorForge.app" "/Applications/FloorForge.app" "$HOME/Applications/FloorForge.app"; do
    if [ -x "$APP/Contents/MacOS/FloorForge" ]; then
        exec "$APP/Contents/MacOS/FloorForge" "$@"
    fi
done

echo "Nie znaleziono FloorForge.app obok tego pliku ani w Programach."
echo "Trzymaj FloorForge.app, Uruchom.command i VERSION razem w jednym folderze."
exit 1
