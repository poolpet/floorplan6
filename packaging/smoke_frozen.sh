#!/usr/bin/env bash
# packaging/smoke_frozen.sh — --selftest na zamrożonej binarce (bez AC, bez okna).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/dist/FloorForge.app/Contents/MacOS/FloorForge"
[ -x "$BIN" ] || { echo "Brak binarki: $BIN — uruchom build_release.sh"; exit 2; }
OUT="$("$BIN" --selftest 2>&1 | tail -20)"
echo "$OUT"
echo "$OUT" | grep -q "SELFTEST OK" || { echo "SMOKE FAIL"; exit 1; }
echo "SMOKE OK"
