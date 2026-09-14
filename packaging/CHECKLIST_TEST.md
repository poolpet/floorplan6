# Test bety na czystym koncie (bramka wysyłki)

Bramka przed wysłaniem paczki testerom. Przechodzi ją **właściciel repo**, raz na paczkę.
Dopóki nie ma 13/13 OK — zip nie wychodzi i **tag `v0.7-beta1` nie jest nadawany**.

Przygotowanie (raz): Ustawienia → Użytkownicy → dodaj konto „beta-test" (standardowe). Zaloguj się na nie.
Na koncie NIE ma: Pythona z brew, venv, repo FloorPlan6. Jest: ArchiCAD 29.

Paczka: `packaging/dist/FloorForge-beta-<wersja>.zip` (buduje `packaging/build_release.sh`,
smoke z paczki: `packaging/smoke_frozen.sh`).

---

## Krok 0 — bramka live `activate_story` (PRZED checklistą, na koncie roboczym)

Tylko właściciel repo, na **swoim** koncie, przy otwartym AC z projektem **2-kondygnacyjnym**
i bezczynnym (nic nie rysujesz, AC nie liczy):

```bash
PYTHONPATH=. python notebooks/ac_story_switch_probe.py
```

Wklej linię `ZWYCIĘZCA: …` do `docs/STATE.md`. Zwycięski kształt przesuń na **początek**
listy `TapirConnection.CHANGE_WINDOW_SHAPES` w `bridge/tapir_connection.py` → przebuduj paczkę
(`packaging/build_release.sh`) → dopiero wtedy checklista poniżej.

`ZWYCIĘZCA: BRAK` (żaden kształt nie przełączył kondygnacji) = auto-przełączanie nie działa
na tym AC → patrz krok 10, wariant B. To nie blokuje bety.

---

## Checklist (konto „beta-test")

| # | Krok | Oczekiwane | OK? |
|---|---|---|---|
| 1 | Skopiuj zip na konto, rozpakuj | 5 pozycji: `FloorForge.app`, `TapirAddOn_AC29_Mac.bundle`, `INSTALACJA.md`, `Uruchom.command`, `VERSION` | |
| 2 | Wykonaj `INSTALACJA.md` §1 (Tapir) | AC startuje, menu Tapir widoczne | |
| 3 | `INSTALACJA.md` §2 — dwuklik `FloorForge.app` → **Ustawienia systemowe → Prywatność i ochrona** → zjedź do komunikatu o „FloorForge" → **„Otwórz mimo to"** | Okno z tytułem `FloorForge <wersja>` (wersja = treść pliku `VERSION`), jedna zakładka „Podział rzutu" | |
| 4 | Pasek AC bez otwartego projektu → **Odśwież** | „Brak połączenia z ArchiCAD — uruchom AC z dodatkiem Tapir i kliknij Odśwież." (bez crasha) | |
| 5 | Otwórz projekt testowy w AC, **Odśwież** | `AC port 19723 · <nazwa projektu> · kondygnacja Parter` | |
| 6 | Mieszkanie: zaznacz ściany obrysu M3 w AC → **„Wczytaj obrys z ArchiCAD"** | podgląd obrysu, typ auto M3 | |
| 7 | **„3. Generuj układy"** | ≥ 1 wariant, podgląd PNG, < 30 s | |
| 8 | **„Wstaw do ArchiCAD"** | strefy + ściany + drzwi + okna + etykiety widoczne w AC | |
| 9 | Dom: obrys 10×8 wpisany ręcznie, tryb Dom → **„3. Generuj układy"** | układ parter + poddasze, ≤ 2 min | |
| 10 | Zaznacz **„Wstaw obie kondygnacje (auto-przełączanie w AC)"** → **Wstaw do ArchiCAD** | zależne od kroku 0 — patrz „Krok 10" niżej; zanotuj wariant A czy B | |
| 11 | Wyłącz AC → **Wstaw do ArchiCAD** | okno „ArchiCAD: Nie znaleziono…", ścieżka logu, bez crasha | |
| 12 | Otwórz `~/Library/Logs/FloorForge/floorforge.log` | wpisy INFO + traceback z kroku 11 | |
| 13 | Dwuklik `Uruchom.command` | aplikacja startuje, terminal pokazuje logi | |

---

## Krok 10 — dwa dopuszczalne wyniki

Krok 10 zależy od osobnej bramki live na `activate_story` (krok 0).

- **Wariant A — probe znalazł działający kształt `ChangeWindow`** (przesunięty na początek
  `CHANGE_WINDOW_SHAPES`): parter ląduje na story 0, poddasze na story 1, **ten sam projekt**,
  jedno kliknięcie. To jest docelowe zachowanie.
- **Wariant B — probe zwrócił `ZWYCIĘZCA: BRAK`:** oczekiwane jest polskie ostrzeżenie
  **„Nie udało się automatycznie przełączyć…"** i **zero wstawionych elementów**
  (świadomie: żadnego częściowego eksportu na złej kondygnacji). Wtedy tester odznacza
  checkbox, przełącza kondygnację ręcznie w AC i wstawia każdą osobno (2 przebiegi).
  Dla bety to też jest **OK** — byle komunikat się pojawił i nic nie zostało wstawione na ślepo.

**Zapisz w `docs/STATE.md`, który wariant wystąpił.**

---

## Wynik

- **13/13 OK** → tag `v0.7-beta1` → wysyłka zipa 2–3 osobom z prośbą:
  „przy błędzie prześlij `~/Library/Logs/FloorForge/floorforge.log` + zrzut ekranu".
- **Dowolny FAIL** → wpis w `docs/STATE.md`, poprawka, ponowny build
  (`packaging/build_release.sh`), powtórz od kroku 1.
