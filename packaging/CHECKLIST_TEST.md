# Test bety na czystym koncie (bramka wysyłki)

Bramka przed wysłaniem paczki testerom. Przechodzi ją **właściciel repo**, raz na paczkę.
Dopóki wszystkie pozycje nie są OK — zip nie wychodzi i **tag `v0.7-beta1` nie jest nadawany**.

Przygotowanie (raz): Ustawienia → Użytkownicy → dodaj konto „beta-test" (standardowe). Zaloguj się na nie.
Na koncie NIE ma: Pythona z brew, venv, repo FloorPlan6. Jest: Archicad 29 na Apple Silicon.

Paczka: `packaging/dist/FloorForge-<wersja>.zip` (buduje `packaging/build_release.sh`,
smoke z paczki: `packaging/smoke_frozen.sh`, instalacja na koncie roboczym: `packaging/install_local.sh`).

---

## Krok 0 — spike kwarantanny (PRZED checklistą)

Wynik spike'u z Task 4 planu: **PENDING (wpisz PASS/FAIL + datę po wykonaniu Task 4 z planu)**

Dopóki tu jest PENDING albo FAIL — nie zaczynaj kroków 1–14 i 4b.

---

## Kroki

| # | Krok | Oczekiwane | OK? |
|---|---|---|---|
| 1 | Pobierz zip Safari na konto beta-test, rozpakuj Finderem | folder `FloorForge-<wersja>/` z `FloorForge.bundle` i `INSTALACJA.md`, bez plików `._*` | |
| 2 | Wykonaj `INSTALACJA.md` (kopia bundla, start AC) | AC startuje bez komunikatów o dodatku; w menu jest „FloorForge"; w Dodatkach nie ma innych kopii FloorForge/FloorPlan4/Tapira (także w ukrytych podfolderach) | |
| 3 | **FloorForge → O FloorForge…** | wersja = `<wersja>` z nazwy zipa, port JSON (np. 19723) | |
| 4 | **FloorForge → Podział rzutu** (bez otwartego projektu) | okno `FloorForge <wersja>`, jedna zakładka „Podział rzutu", pasek `AC port … · (nieznany) · kondygnacja …` **bez klikania Odśwież** | |
| 4b | Okno FloorForge jest ostre na Retinie i wychodzi na wierzch nad AC | tak / tak | |
| 5 | Drugi raz **Podział rzutu** przy otwartym oknie | alert „FloorForge jest już otwarty", drugie okno NIE powstaje | |
| 6 | Otwórz projekt testowy w AC → **Odśwież** w FloorForge | `AC port <ten sam> · <nazwa projektu> · kondygnacja Parter` | |
| 7 | Mieszkanie: zaznacz ściany obrysu M3 → „Wczytaj obrys z ArchiCAD" | podgląd obrysu, typ M3 | |
| 8 | „3. Generuj układy" | ≥ 1 wariant, < 30 s | |
| 9 | „Wstaw do ArchiCAD" | strefy, ściany, drzwi, okna, etykiety w AC | |
| 10 | Dom 10×8 ręcznie, tryb Dom → „3. Generuj układy" | parter + poddasze, ≤ 2 min | |
| 11 | „Wstaw obie kondygnacje (auto-przełączanie w AC)" → Wstaw | parter na story 0, poddasze na story 1, ten sam projekt; **FAIL** gdy obie na jednej story bez ostrzeżenia; ostrzeżenie „Nie udało się automatycznie przełączyć…" + zero wstawionych = **FAIL do zgłoszenia** (auto-switch przeszedł bramkę #1, więc nie powinno wystąpić) | |
| 12 | Zamknij okno FloorForge, zamknij AC (Cmd+Q), uruchom AC → Podział rzutu | okno startuje ponownie (proces nie „wisi" po zamknięciu AC) | |
| 13 | Wyłącz AC przy otwartym oknie FloorForge → „Wstaw do ArchiCAD" | dialog „ArchiCAD: Uruchomiono z ArchiCADa, ale AC nie odpowiada…" ze ścieżką logu, bez crasha | |
| 14 | Otwórz `~/Library/Logs/FloorForge/floorforge.log` | wpisy INFO (`connect: port z FLOORFORGE_AC_PORT=…`) + traceback z kroku 13 | |

---

## Wynik

Krok 0 = PASS **i** wszystkie pozycje z kroków 1–14 i 4b (razem 15) OK:

1. tag `v0.7-beta1`,
2. FF gałęzi do `main`,
3. wysyłka zipa 2–3 osobom — z notką „przy błędzie prześlij log + zrzut".

Dowolny FAIL: wpis do `docs/STATE.md`, poprawka, rebuild paczki, checklista od kroku 1.
