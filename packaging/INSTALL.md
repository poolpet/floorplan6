# FloorForge — installation (macOS, Archicad 29)

**A Mac with Apple Silicon (M1 or newer) and Archicad 29 is required.** FloorForge will not start on Intel Macs.

1. Quit Archicad (Cmd+Q).
2. Copy `FloorForge.bundle` into `/Applications/Graphisoft/Archicad 29/Add-Ons/`
   (on a Polish installation the folder is called `Dodatki`).
   If you already have `TapirAddOn_AC29_Mac.bundle` or `FloorPlan4.bundle` there (FloorForge replaces them) —
   move them out of the Add-Ons folder (e.g. to the Desktop) — Archicad also loads subfolders of Add-Ons, including hidden ones.
   The `install_local.sh` installer does this for you: it puts them in
   `~/Library/Application Support/FloorForge/backups/<date>`, that is outside the Add-Ons folder.
3. Start Archicad. **FloorForge → Room layout** appears in the menu bar.

If something does not work: **FloorForge → About FloorForge…** shows the version and the port; the application log is in
`~/Library/Logs/FloorForge/floorforge.log` — send it together with a screenshot.
