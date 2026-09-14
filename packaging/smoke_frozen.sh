#!/usr/bin/env bash
# packaging/smoke_frozen.sh — --selftest na zamrożonej binarce Z PACZKI (bez AC, bez okna).
# Testujemy to, co dostanie tester: rozpakowujemy najnowszy zip do $TMPDIR (poza
# katalogiem iCloud) i odpalamy binarkę stamtąd. Kopia .appa w packaging/dist jest
# ostemplowana przez file providera i nie reprezentuje produktu.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

ZIP="$(ls -t "$HERE"/dist/FloorForge-beta-*.zip 2>/dev/null | head -1 || true)"
[ -n "$ZIP" ] || { echo "Brak paczki: $HERE/dist/FloorForge-beta-*.zip — uruchom build_release.sh"; exit 2; }
echo "== paczka: $(basename "$ZIP")"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/floorforge-smoke.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
ditto -x -k "$ZIP" "$WORK"

BIN="$(find "$WORK" -type f -path '*/FloorForge.app/Contents/MacOS/FloorForge' 2>/dev/null | head -1 || true)"
[ -x "${BIN:-}" ] || { echo "SMOKE FAIL: w paczce nie ma FloorForge.app/Contents/MacOS/FloorForge"; exit 1; }

# `|| true` jest konieczne: przy selfteście kończącym się 1 errexit ubiłby skrypt
# PRZED echo, a tester zobaczyłby pustkę zamiast przyczyny.
OUT="$("$BIN" --selftest 2>&1 | tail -20 || true)"
echo "$OUT"
echo "$OUT" | grep -q "SELFTEST OK" || { echo "SMOKE FAIL"; exit 1; }
echo "SMOKE OK"
