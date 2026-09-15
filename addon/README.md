# FloorForge — dodatek Archicada

Fork [Tapir Archicad Automation](https://github.com/ENZYME-APD/tapir-archicad-automation)
(licencja MIT — patrz `LICENSE`; lista zmian względem upstreamu w `NOTICE`).
To jest **kod dodatku C++**; aplikacja Pythona żyje w katalogu nadrzędnym.

## Co robi

- rejestruje komendy JSON w przestrzeni **`FloorForgeCommand`** (strefy, ściany, drzwi,
  kondygnacje, właściwości) — to nimi aplikacja rozmawia z Archicadem;
- dokłada menu **FloorForge → Podział rzutu**, które uruchamia osadzonego Pythona
  z `FloorForge.bundle/Contents/Resources/FloorForge/FloorForge` i przekazuje mu port
  JSON w `FLOORFORGE_AC_PORT` (plus `FLOORFORGE_LAUNCHED_FROM_AC`);
- **FloorForge → O FloorForge…** pokazuje wersję i aktywny port JSON.

## Budowanie (macOS, Apple Silicon)

```sh
cmake -S addon -B addon/Build -DAC_VERSION=29 \
      -DAC_API_DEVKIT_DIR="<ścieżka do DevKitu>/Support" \
      -DFLOORFORGE_VERSION=dev \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build addon/Build --config RelWithDebInfo -j8
```

`-DCMAKE_OSX_ARCHITECTURES=arm64` jest obowiązkowe: osadzony Python jest arm64-only,
więc dodatek też musi być — inaczej na Intelu Archicad załaduje dodatek, a start aplikacji padnie.

## Paczka dla testera

`packaging/build_release.sh` — buduje dodatek, dokłada osadzonego Pythona (PyInstaller),
podpisuje ad-hoc, pakuje do zipa i przepuszcza go przez bramkę (AppleDouble, codesign,
Mach-O, architektura, Info.plist, selftest).
