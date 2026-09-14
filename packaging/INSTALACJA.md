# FloorForge — beta (macOS, ArchiCAD 29)

## 1. Dodatek Tapir (jednorazowo)
1. Zamknij ArchiCAD.
2. Skopiuj `TapirAddOn_AC29_Mac.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`
   (jeśli masz tam już inny `TapirAddOn…bundle`, przenieś go gdzie indziej — FloorForge wymaga tej wersji).
3. Uruchom ArchiCAD i otwórz projekt.

## 2. Aplikacja
1. Przenieś `FloorForge.app` do `Programy` (lub gdziekolwiek).
2. Pierwsze otwarcie: **prawy klik → Otwórz → Otwórz** (aplikacja nie jest notaryzowana w Apple; to jednorazowe).
   Jeśli macOS mimo to blokuje: Ustawienia → Prywatność i ochrona → „Otwórz mimo to".
3. W oknie na górze zobaczysz „AC port 19723 · nazwa projektu · kondygnacja …". Jeśli „Brak połączenia": sprawdź, że AC działa i kliknij „Odśwież".

## 3. Praca
1. W AC zaznacz ściany obrysu mieszkania (albo strefę / płytę) → w FloorForge „Wczytaj obrys z ArchiCAD".
2. Wybierz tryb (mieszkanie M1–M5 / dom) → „Generuj układy" (mieszkanie kilka sekund, dom do ~2 min).
3. Przeglądaj warianty ‹ › → „Wstaw do ArchiCAD". Dom: zaznacz „Wstaw obie kondygnacje".

## 4. Gdy coś nie działa
- Okno błędu podaje przyczynę i ścieżkę logu. Prześlij plik `~/Library/Logs/FloorForge/floorforge.log` + zrzut ekranu.
- Awaryjnie: dwuklik `Uruchom.command` (uruchamia aplikację z terminalem — widać pełny komunikat).
  Plik `Uruchom.command` i `VERSION` muszą zostać w tym samym folderze co `FloorForge.app`.
