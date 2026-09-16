# FloorForge — natywna paleta w Archicadzie („poziom 1") (design)

> Data: 2026-09-16. Decyzja Dawida: beta idzie z **paletą w Archicadzie zamiast osobnego okna PyQt**
> (jak FloorPlan4_CPP). Mózg i writer zostają w Pythonie, który działa w tle jako serwis HTTP
> osadzony w tym samym `FloorForge.bundle`. Buduje na: `2026-09-15-floorforge-bundle-design.md`
> (bundle, launcher, pakowanie) i na istniejącym `service/` (`/health`, `/solve`, `/jobs/{id}`).
> Decyzja A: geometrię do AC wstawia Python (istniejący `bridge/plan_writer` + `house_writer`).
> Natywny `PlanWriter` z FP4_CPP = poziom 2, poza zakresem.

## 1. Cel i zakres

**Cel:** architekt w Archicadzie 29 otwiera **FloorForge → Palette**, wczytuje obrys z zaznaczenia
albo klikiem w pomieszczenie, klika **Generate**, przegląda warianty w podglądzie palety i klika
**Insert into Archicad**. Nie widzi żadnego okna poza Archicadem. Instalacja bez zmian: kopia
bundla do Add-Ons.

**W zakresie (v1):**
- Paleta DG (modeless, z FP4_CPP: `FloorPlanPalette` + `.grc`, uproszczona): obrys z zaznaczenia
  / z punktu, tryb Apartment/House, typ M1–M5 (auto), liczba wariantów, Generate z paskiem
  postępu, `<` `>` po wariantach, podgląd wariantu rysowany natywnie z kontraktu JSON, Insert
  (dom: checkbox „Insert both storeys"), stopka ze stanem serwisu.
- Serwis Pythona (`service/`): tryb `--serve` bez okna, plik portu, `POST /solve` czytający obrys
  z AC (`source: selection|point`), wyniki trzymane w pamięci, `POST /export` wstawiający wybrany
  wariant przez istniejące writery, angielskie komunikaty błędów.
- Launcher C++: zamiast okna spawnuje serwis (lazy, przy pierwszym otwarciu palety), pilnuje
  jego życia, kończy z AC.
- Testy: pytest dla serwisu (mocki AC + realny solve M2), test kontraktu podglądu; C++ bez
  testów jednostkowych (jak Tapir/CLT), ręczna checklista.

**Poza zakresem:** natywny writer C++ (poziom 2), Windows, notaryzacja, ręczne wpisywanie
wymiarów/obrysu w palecie, edytor fasad/wejścia (wejście = z drzwi w zaznaczonych ścianach jak
dziś, fallback: najdłuższa ściana), meble w podglądzie (writer wstawia je jak dziś, jeśli włączone
w serwisie — v1: meble OFF), tryb parcelacji, okno PyQt (zostaje jako narzędzie dev:
`floorforge_app.py` bez argumentów).

## 2. Architektura

```
Archicad 29
 ├─ FloorForge.bundle (C++)
 │    ├─ komendy JSON „FloorForgeCommand" (jak dziś — writer Pythona z nich korzysta)
 │    ├─ menu: FloorForge → Palette | About FloorForge...
 │    ├─ FloorForgePalette (DG::Palette): UI + podgląd + HTTP do serwisu
 │    └─ ServiceSupervisor: spawn/health/kill osadzonego serwisu
 └─ (proces potomny) Contents/Resources/FloorForge/FloorForge --serve
        ├─ service/app.py: /health /solve /jobs/{id} /export /shutdown
        ├─ bridge/boundary_reader (czyta obrys z AC przez komendy JSON)
        ├─ core/* (mózg — bez zmian)
        └─ bridge/plan_writer + house_writer (wstawianie do AC przez komendy JSON)
```

Przepływ: paleta → `POST /solve {source, mode, ...}` → serwis czyta obrys z AC (port z
`FLOORFORGE_AC_PORT`), liczy warianty w wątku, trzyma obiekty `FloorPlan`/`TwoStoreyLayout` w
`ResultStore` → paleta odpytuje `GET /jobs/{id}` (postęp, po zakończeniu: kontrakty JSON
wariantów do podglądu) → `POST /export {job_id, variant, storeys}` → serwis wstawia do AC →
paleta pokazuje podsumowanie.

## 3. Serwis Pythona — zmiany

### 3.1 Tryb `--serve` (`floorforge_app.py`)
- `FloorForge --serve` (env od launchera: `FLOORFORGE_AC_PORT`, `FLOORFORGE_VERSION`,
  `FLOORFORGE_LAUNCHED_FROM_AC=1`): bez Qt, `setup_logging()`, `start_server(port=0)`, zapis
  pliku portu `~/Library/Application Support/FloorForge/service-<AC_PORT>.port` (treść:
  `PORT=<n>\nPID=<pid>\nVERSION=<ver>\n`), potem czeka; kończy się na `POST /shutdown`, SIGTERM,
  albo gdy **proces rodzica (AC) zniknie** (watchdog: `os.getppid()` co 2 s; PyInstaller: rodzic =
  AC, bo spawn bez pośrednika). Przy wyjściu usuwa plik portu.
- `--selftest` i `--ac-probe` bez zmian; brak argumentów = okno dev (bez zmian).

### 3.2 Endpointy (`service/app.py`)
| Metoda | Ścieżka | Wejście | Wyjście |
|---|---|---|---|
| GET | `/health` | — | `{status, version, ac_port, ac_connected: bool}` (sprawdza `TapirConnection` cache, bez skanu) |
| POST | `/solve` | `{"source":"selection"|"point"|"polygon", "point":[x,y]?, "polygon":[...]?, "entry":[x,y]?, "mode":"apartment"|"house", "mtype":"M2"?, "max_variants":5 (0 = tylko obrys), "min_score":0.5, "num_storeys":2}` | `202 {"job_id"}` |
| GET | `/jobs/{id}` | — | job dict; po `done`: `result = {"mode", "boundary": {polygon, entry, area, auto_type}, "variants":[{index, score, contract}] }` (dom: 1 wariant, `contract = {"parter":…, "poddasze":…}`) |
| POST | `/export` | `{"job_id", "variant": 0, "storeys": ["parter"] | ["parter","poddasze"], "furniture": false}` | `200 {"zones":n,"walls":n,"doors":n,"windows":n,"labels":n,"storeys":[...]}`; `404` brak joba/wariantu; `409` job nie `done`; `503` AC nie odpowiada; `422` błąd writera (np. brak kondygnacji nad parterem) z angielskim `error` |
| POST | `/shutdown` | — | `200`, serwer kończy pracę |

- `source: selection` → `bridge.boundary_reader.read_boundary_from_archicad` (jak przycisk „Load
  outline"); `source: point` → `read_boundary_from_point(x, y)` (jak inner edge, bez pollingu:
  paleta podaje punkt kliknięty natywnie); `source: polygon` → jak dziś (`--selftest`, testy).
- Odczyt obrysu i solve dzieją się w wątku joba; błędy odczytu → `status: error`, `error` po
  angielsku (mapa jak `ui/user_errors.describe`, ale bez Qt: `service/errors.py: describe(exc)
  -> {"title","text"}`; `ui/user_errors.py` deleguje do niej, żeby nie dublować).
- `ResultStore` (`service/results.py`): `job_id → {"mode", "boundary", "plans": [FloorPlan] |
  "layout": TwoStoreyLayout, "created": ts}`; limit 20 ostatnich jobów (LRU), reszta usuwana.
- `/export` dla apartment: `export_plan_to_archicad(plan, tapir=<połączenie z FLOORFORGE_AC_PORT>,
  include_furniture=furniture)`; dla house: pętla po `storeys` z `activate_story` jak w GUI
  (`_export_house_to_archicad` — logika przeniesiona do `bridge/house_export.py:
  export_house_storeys(layout, storeys, tapir) -> dict` i użyta zarówno przez GUI, jak i serwis;
  GUI dalej pokazuje dialogi, ale decyzje o indeksach i częściowym eksporcie są w jednym miejscu).
- Kontrakt podglądu = `core/plan_contract.plan_to_contract` (rooms z `polygon`, `name`,
  `zone`, `area`) + `score`. Paleta rysuje z `rooms[].polygon` i koloru z `zone`.

### 3.3 Testy
- `tests/test_service_serve.py`: `--serve` pisze plik portu z poprawnym portem, `/health` odpowiada,
  `/shutdown` kończy proces i usuwa plik (subprocess ze źródeł).
- `tests/test_service_export.py`: `/solve source=polygon` M2 8×6 → `done` z ≥1 wariantem;
  `/export` z zamockowanym `export_plan_to_archicad` → 200 i przekazany właściwy `FloorPlan`;
  `404`/`409`/`503`/`422` ścieżki.
- `tests/test_service_errors.py`: `describe` bez Qt, angielskie teksty; `ui/user_errors` deleguje.

## 4. Add-on C++ — paleta i nadzór serwisu

### 4.1 Pliki (w `addon/Sources/`)
- `FloorForgePalette.{hpp,cpp}` — z `FloorPlan4_CPP/Src/FloorPlanPalette.*` (podgląd `UserItem`,
  `drawPreview`, nawigacja, progress) **odchudzone**: bez MPZP, bez parametrów WT/piętra, bez
  ręcznych wymiarów, bez lokalnego solvera. Stan palety = `PaletteState {job_id, variants[],
  current, boundary, mode, busy}`.
- `ServiceClient.{hpp,cpp}` — `HTTP::Client::ClientConnection` + `JSON::JDOMParser` (jak
  `VersionChecker.cpp` z Tapira): `Health()`, `Solve(req) -> job_id`, `Job(id) -> JSON`,
  `Export(req) -> JSON`, `Shutdown()`. Timeouts: health 1 s, solve/jobs 5 s, export 60 s
  (apartament: sekundy; dom obie kondygnacje: do ~20 s — `/export` w v1 jest synchroniczny).
- `ServiceSupervisor.{hpp,cpp}` — `EnsureRunning()`: jeśli `/health` nie odpowiada → spawn
  `Resources/FloorForge/FloorForge --serve` (env jak dziś), czekaj na plik portu (do 15 s, polling
  250 ms), `/health`; `Shutdown()` w `FreeData` (POST `/shutdown`, po 2 s `Process::Kill`).
  Utrzymuje `GS::Process` i port. Błąd → alert „FloorForge service failed to start … log …".
- `FloorForgeLauncher.*` → zastąpiony przez `ServiceSupervisor` (menu „Palette" = pokaż paletę +
  `EnsureRunning()`).
- Zasoby: `GDLG` palety (z FP4_CPP `32600`, skrócona), stringi EN w `RINT/AddOn.grc`.

### 4.2 UI palety (v1, góra → dół)
1. Stopka/pasek stanu: `Service: starting… | ready (v…) | error` + `Archicad port N`.
2. **Outline**: `Load from selection` → `POST /solve {source: selection, max_variants: 0}`;
   `Pick point` → kursor punktu (`ACAPI_Interface(APIIo_GetPointID)`, jak FP4_CPP) →
   `POST /solve {source: point, point: [x,y], max_variants: 0}`. Job z `max_variants: 0` czyta
   tylko obrys (bez solve, <1 s) i zwraca `boundary` (polygon, entry, area, auto_type). Paleta
   rysuje obrys + wejście (kropka) i zapamiętuje `boundary` do pełnego Generate.
3. **Mode**: radio Apartment / House. Apartment: popup typu (Auto/M1–M5; „Auto" = z `boundary.auto_type`),
   liczba wariantów (1–5). House: checkbox `Insert both storeys` (domyślnie ON).
4. **Generate** → `/solve` (pełny), pasek postępu z `/jobs/{id}.progress` (timer 500 ms,
   `DG::Timer`/`ACAPI_ProcessWindow`? → prosty timer palety), przycisk zmienia się w `Cancel`
   (v1: anuluj = przestań odpytywać; solver dokończy w tle).
5. **Preview** (`UserItem` 340×220): pokoje wypełnione kolorem strefy (day/night/service/circulation
   jak w PyQt), nazwa + `area m²`, obrys, wejście; dom: dwa panele obok siebie (Ground floor / Attic).
   `<` `>` + `Variant 2/5 · score 0.87`.
6. **Insert into Archicad** → `/export` → alert z podsumowaniem (`n zones, n walls, …`).
   Dom: obie kondygnacje przez `activate_story` po stronie serwisu; jeśli serwis zwróci
   `partial: true` → alert wymienia wstawione kondygnacje i co zrobić.

### 4.3 Błędy (EN, w palecie i alertach)
- Serwis nie startuje / pada → alert z ścieżką logu; pasek stanu `error`, przycisk `Restart service`.
- `/solve` error (brak zaznaczenia, obrys niepoprawny, INFEASIBLE) → tekst z `error` joba w alercie.
- `/export` 503 → „Archicad JSON port not responding…", 422 → treść z serwisu.

## 5. Pakowanie i instalacja
- Bez zmian w strukturze bundla i skryptach poza: launcher → supervisor (spawn `--serve`);
  bramka paczki dodatkowo uruchamia `--serve` z tymczasowym `FLOORFORGE_AC_PORT=1`, czeka na plik
  portu, `GET /health`, `POST /shutdown` (dowód, że serwis w bundlu wstaje bez Qt).
- `INSTALL.md`/`INSTALACJA.md`: menu „FloorForge → Palette"; Troubleshooting +
  „Service failed to start" (kwarantanna, log).
- `CHECKLIST_TEST.md` przepisany pod paletę (obrys z zaznaczenia i z punktu, M3 → Generate →
  Insert, dom obie kondygnacje, AC zamknięte → serwis znika (`pgrep`), dwa AC → dwa serwisy z
  osobnymi plikami portu, restart serwisu z palety).

## 6. Kolejność wdrożenia
1. Serwis: `describe` bez Qt + `ResultStore` + `/solve source=…` + `/export` + `/shutdown` +
   `--serve` z plikiem portu i watchdogiem rodzica (testy).
2. `bridge/house_export.py` (wspólna logika eksportu obu kondygnacji), GUI przepięte na nią (testy
   istniejące zielone).
3. C++: `ServiceClient` + `ServiceSupervisor` + menu „Palette" z pustą paletą pokazującą `/health`
   (pierwszy build i test live: serwis wstaje z bundla).
4. C++: paleta — outline (selection/point), Generate + postęp, podgląd, nawigacja.
5. C++: Insert (+ obie kondygnacje), alerty, stopka.
6. Pakowanie: bramka `--serve`, docs, checklist; pełny pytest; build; live: checklist.

## 7. Ryzyka
- **Wywołanie HTTP z głównego wątku AC** blokuje UI na czas żądania → tylko krótkie żądania
  (health/solve/jobs ≤ 1–2 s); solve i eksport liczą się po stronie serwisu, paleta odpytuje timerem.
  Eksport domu (do ~20 s) w v1 blokuje AC na czas wstawiania — akceptowalne (writer i tak pisze do
  tego AC); jeśli boli → v1.1: `/export` jako job.
- **Serwis-sierota**: watchdog `getppid` + `FreeData` + plik portu per AC; przy starcie
  `EnsureRunning` sprząta martwy plik portu (PID nie żyje).
- **Dwa AC**: dwa serwisy, pliki `service-19723.port`, `service-19724.port`; każdy serwis łączy
  się wyłącznie z portem z env (żadnego skanu).
- **Podgląd**: kontrakt ma polygony w metrach; paleta skaluje do `UserItem` jak FP4_CPP.
- **Wstawianie przez własne komendy JSON z procesu potomnego**: działa dziś (okno PyQt); paleta
  niczego tu nie zmienia.
