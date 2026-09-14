# FloorForge — beta (macOS, ArchiCAD 29)

## 1. Dodatek Tapir (jednorazowo)
1. Zamknij ArchiCAD.
2. Skopiuj `TapirAddOn_AC29_Mac.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`
   (jeśli masz tam już inny `TapirAddOn…bundle`, przenieś go gdzie indziej — FloorForge wymaga tej wersji).
3. Uruchom ArchiCAD i otwórz projekt.

## 2. Aplikacja

> **Nie rozdzielaj plików z paczki.** `FloorForge.app`, `Uruchom.command` i `VERSION`
> muszą zostać w jednym folderze — bez `VERSION` aplikacja nie zna swojej wersji,
> a `Uruchom.command` nie znajdzie `.appa`.

1. Przenieś **cały rozpakowany folder** (nie sam `FloorForge.app`) tam, gdzie ma
   mieszkać — np. `~/Programy/FloorForge/` albo na Biurko. Uruchamiaj stamtąd.
2. Pierwsze otwarcie — aplikacja nie jest notaryzowana w Apple, więc macOS ją zatrzyma.
   To jednorazowe:
   - Dwuklik w `FloorForge.app` → pojawi się komunikat, że nie da się otworzyć.
   - **Ustawienia systemowe → Prywatność i ochrona** → zjedź na dół do komunikatu
     o zablokowanym „FloorForge" → **„Otwórz mimo to"** → potwierdź hasłem/Touch ID.
   - *(Starsze macOS: działa też skrót prawy klik na `FloorForge.app` → **Otwórz** → **Otwórz**.
     Na macOS 15+ ten skrót już nie wystarcza — użyj drogi przez Ustawienia.)*
   - `Uruchom.command` po pobraniu jest objęty tą samą kwarantanną. Przy pierwszym
     dwukliku przejdź tą samą drogą, albo w Terminalu:
     `xattr -d com.apple.quarantine /ścieżka/do/Uruchom.command`
3. Na pasku statusu AC (w lewym panelu) zobaczysz jeden z trzech stanów:
   - **`ArchiCAD: nie sprawdzono`** — stan startowy. Aplikacja **nie skanuje AC sama**;
     ten napis widnieje do pierwszego kliknięcia **Odśwież**. To normalne, nie błąd.
   - `AC port 19723 · nazwa projektu · kondygnacja …` — połączenie działa.
   - „Brak połączenia z ArchiCAD…" — sprawdź, czy AC działa z dodatkiem Tapir,
     i kliknij **Odśwież** ponownie.

## 3. Praca
1. W AC zaznacz ściany obrysu mieszkania (albo strefę / płytę) → w FloorForge
   **„Wczytaj obrys z ArchiCAD"** (sekcja `1. Outline`).
2. W `2. Type and options` wybierz tryb (mieszkanie M1–M5 / dom) → **„3. Generuj układy"**
   (mieszkanie kilka sekund, dom do ~2 min).
3. W `4. Result` przeglądaj warianty przyciskami **`<<`** / **`>>`** → **„Wstaw do ArchiCAD"**.
   Dom: zaznacz **„Wstaw obie kondygnacje (auto-przełączanie w AC)"**.

> W tej becie nagłówki sekcji są jeszcze po angielsku (`1. Outline`,
> `2. Type and options`, `4. Result`) — przyciski i komunikaty są po polsku.

## 4. Gdy coś nie działa
- Okno błędu podaje przyczynę i ścieżkę logu. Prześlij plik
  `~/Library/Logs/FloorForge/floorforge.log` + zrzut ekranu.
- Awaryjnie: dwuklik `Uruchom.command` — uruchamia aplikację z terminalem, widać
  pełny komunikat. Musi leżeć w tym samym folderze co `FloorForge.app` i `VERSION`.
