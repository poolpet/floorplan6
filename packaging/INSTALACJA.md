# FloorForge — instalacja (macOS, Archicad 29)

**Wymagany Mac z Apple Silicon (M1 lub nowszy) i Archicad 29.** Na Macach Intel FloorForge się nie uruchomi.

1. Zamknij Archicad (Cmd+Q).
2. Skopiuj `FloorForge.bundle` do `/Applications/Graphisoft/Archicad 29/Dodatki/`.
   Jeśli masz tam dodatek FloorPlan4 albo Tapir (FloorForge je zastępuje) — przenieś je poza
   Dodatki, np. na Biurko. Archicad wczytuje też ukryte podfoldery Dodatków, więc kopia
   zostawiona w środku również zostanie załadowana (Cmd+Shift+. w Finderze pokazuje ukryte).
3. Uruchom Archicad. W pasku menu pojawi się **FloorForge → Room layout**.

Gdy coś nie działa: **FloorForge → About FloorForge...** pokazuje wersję i port; log aplikacji jest w
`~/Library/Logs/FloorForge/floorforge.log` — prześlij go razem ze zrzutem ekranu.

## Gdy coś nie działa

**Nie ma menu FloorForge.** Otwórz Opcje → Menedżer dodatków i poszukaj FloorForge na liście;
jeśli jest, ale się nie załadował, najbardziej prawdopodobny powód to procesor — bundle jest
tylko na Apple Silicon i Archicad na Macu z Intelem go nie wczyta. Jeśli przy starcie pojawia się
komunikat o dodatkach, których nie dało się załadować, sprawdź w Dodatkach inne kopie FloorForge,
FloorPlan4 albo Tapira — także w ukrytych podfolderach (punkt 2).

**„Room layout" nic nie robi albo okno pojawia się i znika.** macOS oznacza kwarantanną pliki
pobrane z internetu i ubija osadzoną aplikację. Zdejmij flagę w Terminalu i uruchom Archicada
ponownie:

```sh
xattr -dr com.apple.quarantine "/Applications/Graphisoft/Archicad 29/Dodatki/FloorForge.bundle"
```

**Gdzie jest log.** `~/Library/Logs/FloorForge/floorforge.log` — otwórz w Konsoli albo TextEdit.
Dołączaj go do każdego zgłoszenia razem ze zrzutem ekranu; ostatnie linie mówią, na którym porcie
Archicada działał FloorForge, i zawierają pełny błąd.
