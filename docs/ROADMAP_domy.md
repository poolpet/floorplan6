# FloorPlan6 — ROADMAP: rzuty domów

> Ustalenia strategiczne z 2026-05-31. Nadrzędne wobec starszej mapy 4-etapowej w `docs/`.

## Decyzja w jednym zdaniu

Zamrażamy Etapy 1, 2 i 3. Cała energia idzie w **Etap 4 (silnik CP-SAT)** napędzany realną potrzebą: **rzuty domów** (wolnostojący → bliźniak → szeregowiec).

Dlaczego: Etap 4 jest już stabilny — jego wartość ujawnia się dopiero, gdy gnasz go realnymi przypadkami. Rozwiązywanie problemu domów JEST dokończeniem Etapu 4. Etap 3 (podział piętra na mieszkania) służy budynkom wielorodzinnym i nie przybliża domów.

## Co zamrożone (zero pracy teraz)

| Etap | Co to | Status | Działanie |
|---|---|---|---|
| 1 | Podział działki (MPZP) | rozbudowany (sesja 14) | freeze **w miejscu**, oznaczyć legacy w docs/UI. NIE wydzielać do osobnego modułu/appki teraz. |
| 2 | Generator brył | niezaczęty | freeze |
| 3 | Podział piętra na mieszkania (wielorodzinne) | MVP dla prostokątów, known issue L-shape | freeze (bez domykania) |

Kryterium powrotu do Etapu 1: dopiero gdy (a) wznawiasz jego aktywny rozwój, albo (b) chcesz wydać go samodzielnie. Dopóki nie — wydzielanie to przedwczesna optymalizacja.

## Główny tor — DOMY

Bazuje na gałęzi `feat/sfh-2storey-mvp` (Plan 1 zrobiony: `core/house_layout.py`, `generate_house` 2 kondygnacje, templates `house_parter/pietro.json`).

**Kolejność typów:**
1. **Wolnostojący jednorodzinny** — pełny obrys, bez ścian wspólnych. Tu dopracowujesz silnik 2-kondygnacyjny + meble.
2. **Bliźniak** — 1 ściana wspólna, mirror.
3. **Szeregowiec** — 2 ściany wspólne, wąski głęboki obrys.

Sąsiadujące obrysy (bliźniak/szereg) rysujesz ręcznie w AC — Etap 1 zamrożony, nie jest potrzebny.

**Kroki:**
1. **Merge `feat/sfh-2storey-mvp` → main.** Pierwszy ruch — bez tego reszta stoi na piasku (7 commitów wisi poza main).
2. **Plan 2 — meble** (`core/furniture.py`): regułowe zestawy per pokój pod ściany, z dala od drzwi + render. Zaprojektowane w spec §5.
3. **Plan 3 — viz + UI**: render 2 kondygnacji, tryb „dom 2-kond." w Etapie 4, routing JEDNORODZINNA, przełącznik mebli.
4. **GAP jakości (architektoniczny):** dla domu dystrybucja nadmiaru ≠ apartament. Q6 dumpuje nadmiar w salon (salon 48 m²). Trzeba cap rozsądnych rozmiarów pokoi domowych albo „nadmiar → taras / hol / garaż". Decyzja Dawida, nie zgadywanie.
5. Walidacja na realnym ~64 m²/kondygnację (na za dużym footprincie widać artefakt nadmiaru).

## Stack: Python vs C++

Rozdziel dwie warstwy:

- **Mózg** (solver, układ pokoi, meble, reguły CLT) → **Python, prawdopodobnie na zawsze.** Pisanie algorytmu w C++ teraz = powtórzenie błędu z 29.04 (buggy geometria C++ była powodem powrotu do Pythona).
- **Powłoka** (integracja z AC, „natywne uczucie") → **C++ Tapir add-on** (`tapir-custom/`, port 19723). Już to masz. Wygodę uruchamiania zwiększasz pogrubiając powłokę (przycisk w AC → odpala pipeline Pythona w tle) + pakując Pythona (PyInstaller), NIE przepisując algorytmu.

„Python first, potem C++" = tak, ale „potem-C++" to decyzja **dystrybucyjna** dla zamrożonego produktu, nie decyzja o szybkości rozwoju.

## CLT

Dawid projektuje teraz w CLT (drewno klejone krzyżowo). Gdy stanie się istotne, wchodzi jako nowa warstwa reguł w `rules/` (jak WT 2002) + ograniczenia w solverze: siatka paneli, ściany nośne, rozpiętości. Te reguły będą się zmieniać → kolejny argument za mózgiem w Pythonie.

## Najbliższy konkret

→ Decyzja o merge gałęzi `feat/sfh-2storey-mvp` do main.
