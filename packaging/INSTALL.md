# FloorForge — installation (macOS, Archicad 29)

**A Mac with Apple Silicon (M1 or newer) and Archicad 29 is required.** FloorForge will not start on Intel Macs.

1. Quit Archicad (Cmd+Q).
2. Copy `FloorForge.bundle` into `/Applications/Graphisoft/Archicad 29/Add-Ons/`
   (on a Polish installation the folder is called `Dodatki`).
   If you had a FloorPlan4 or Tapir add-on there (FloorForge replaces them) — move them out of
   the Add-Ons folder, for example to the Desktop. Archicad also reads hidden subfolders of
   Add-Ons, so a copy left inside gets loaded too (press Cmd+Shift+. in Finder to see them).
3. Start Archicad. **FloorForge → Room layout** appears in the menu bar.

If something does not work: **FloorForge → About FloorForge...** shows the version and the port; the application log is in
`~/Library/Logs/FloorForge/floorforge.log` — send it together with a screenshot.

## Troubleshooting

**The FloorForge menu is missing.** Open Options → Add-On Manager and look for FloorForge in the
list; if it is there but not loaded, the most likely reason is the processor — the bundle is
Apple Silicon only and Archicad on an Intel Mac will not load it. If a message about add-ons that
could not be loaded appears at startup, check the Add-Ons folder for other copies of FloorForge,
FloorPlan4 or Tapir, including hidden subfolders (step 2).

**"Room layout" does nothing, or the window shows up and disappears.** macOS quarantines files
downloaded from the internet and kills the embedded application. Remove the flag in Terminal and
restart Archicad:

```sh
xattr -dr com.apple.quarantine "/Applications/Graphisoft/Archicad 29/Add-Ons/FloorForge.bundle"
```
(On a Polish Archicad the folder is `Dodatki` instead of `Add-Ons` — use the path where you copied the bundle.)

(on an English installation the folder is `Add-Ons` instead of `Dodatki`).

**Where the log is.** `~/Library/Logs/FloorForge/floorforge.log` — open it in Console or
TextEdit. Send it with a screenshot when reporting anything; the last lines say which Archicad
port FloorForge used and carry the full error.
