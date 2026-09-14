#!/usr/bin/env bash
# Uruchom.command — awaryjne uruchomienie FloorForge z widocznym terminalem.
# Binarka odpalona z shella nie dostaje LSEnvironment z Info.plist, więc tryb bety
# i wersję (plik VERSION leżący obok .app) ustawiamy tutaj.
DIR="$(cd "$(dirname "$0")" && pwd)"   # liczymy PRZED cd — $0 bywa ścieżką względną
cd "$DIR"
export FLOORFORGE_BETA=1
VER="$(cat "$DIR/VERSION" 2>/dev/null || true)"
export FLOORFORGE_VERSION="${VER:-beta}"
exec "$DIR/FloorForge.app/Contents/MacOS/FloorForge" "$@"
