# FloorForge — instalacja (macOS, Archicad 29)

**Wymagany Mac z Apple Silicon (M1 lub nowszy) i Archicad 29.** Na Macach Intel FloorForge się nie uruchomi.

1. Zamknij Archicad (Cmd+Q).
2. Skopiuj `FloorForge.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`.
   Jeśli masz tam `TapirAddOn_AC29_Mac.bundle` albo `FloorPlan4.bundle` (FloorForge je zastępuje) —
   przenieś je poza Dodatki (np. na Biurko) — Archicad wczytuje też podfoldery Dodatków, także ukryte.
   Instalator `install_local.sh` robi to sam: odkłada je do
   `~/Library/Application Support/FloorForge/backups/<data>`, czyli poza Dodatki.
3. Uruchom Archicad. W pasku menu pojawi się **FloorForge → Podział rzutu**.

Gdy coś nie działa: **FloorForge → O FloorForge…** pokazuje wersję i port; log aplikacji jest w
`~/Library/Logs/FloorForge/floorforge.log` — prześlij go razem ze zrzutem ekranu.
