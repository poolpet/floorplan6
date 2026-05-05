# OPEN_QUESTIONS — pytania architektoniczne do decyzji

> **Zasada:** zanim Claude zaimplementuje cokolwiek związanego z poniższymi pytaniami — MUSI zapytać Dawida i poczekać na decyzję. NIE zgadywać. Reguła B5.

> **Format:** każde pytanie ma kontekst (skąd przyszło), opcje (a/b/c), domyślną rekomendację (jeśli jest sensowna) i status (OPEN / DECIDED).

---

## ETAP 1 — PLOT SUBDIVISION (z C++ FloorPlan4_CPP sesja 29.04)

> **Status etapu:** ⏸️ ODŁOŻONE w FloorPlan6 do osobnej sesji. Najpierw etap 4 (rzuty mieszkań).
>
> **Kontekst:** w C++ Plot Subdivider miał 4 znane bugi (sub-działki wystają poza granicę, drogi wystają, strefa budowlana ignorowana, 36 stref dla 10 możliwych). Reimplementacja w Pythonie z Shapely + matplotlib. Te decyzje są wymagane PRZED implementacją.

### Q1: Sub-działki przy nieregularnej granicy
**Pytanie:** co robić z sub-działką która wpadałaby częściowo poza granicę działki głównej (lub poza strefę budowlaną)?

**Opcje:**
- (a) **Przyciąć do granicy** → sub-działka ma kształt trapezu (analogia z trapezowymi mieszkaniami z FloorPlan2/4 — istnieje `core/trapezoid_handler.py`)
- (b) **Odrzucić całkowicie** → tylko pełnoprawne prostokąty
- (c) **Zmniejszyć** → mniejszy prostokąt który mieści się w środku

**Rekomendacja:** (a) — istnieje już infrastruktura trapez handler. Ale to decyzja Dawida.

**Status:** OPEN

### Q2: Układ dróg wewnętrznych
**Pytanie:** jak prowadzić drogi wewnętrzne między sub-działkami?

**Opcje:**
- (a) **Pasy między rzędami** (prosty grid — obecnie zaimplementowane w C++)
- (b) **Jedna główna droga (kręgosłup)** + krótkie dojścia do każdej działki
- (c) **Pętla / sięgacz / inny układ**

**Rekomendacja:** brak — czysto architektoniczna decyzja. Dawid wie jak to wygląda w realnych projektach.

**Status:** OPEN

### Q3: Czy front sub-działki musi być przy drodze?
**Pytanie:** czy każda sub-działka MUSI mieć krótszy bok przy drodze (front)?

**Opcje:**
- (a) **TAK** — krótszy bok = front, dłuższy bok = bok parceli (standard PL)
- (b) **NIE** — może być na odwrót (głębsza działka dłuższa od ulicy)
- (c) **Zależy od typu zabudowy** — szeregowa TAK, wolnostojąca obojętnie

**Status:** OPEN

### Q4: BLIZNIACZA — definicja sub-działki
**Pytanie:** jak liczyć sub-działkę dla zabudowy bliźniaczej?

**Opcje:**
- (a) **1 sub-działka = 1 segment** (1 lokal). Para to 2 sąsiednie sub-działki ze wspólną ścianą. (obecnie w C++)
- (b) **1 sub-działka = 1 cały budynek bliźniaczy** (2 lokale w jednym budynku)

**Status:** OPEN

### Q5: Orientacja siatki sub-działek
**Pytanie:** jaką orientację ma mieć siatka sub-działek?

**Opcje:**
- (a) **Aligned z najdłuższą krawędzią działki** (auto)
- (b) **Aligned z user-marked external access edge** (z palety AC, wymaga interakcji)
- (c) **Optymalizacja** dla maksymalnego wykorzystania działki (algorytm szuka)

**Rekomendacja:** (b) — daje user controlu, prosty UX (jeden click "oznacz dostęp do drogi" — jest już w paletcie C++).

**Status:** OPEN

---

## ETAP 4 — RZUTY MIESZKAŃ (NOWE Q POJAWIAJĄ SIĘ TUTAJ PO PIERWSZEJ SESJI)

### Q6: Łazienka — kto absorbuje "extra area"?
**Pytanie:** jeśli polygon mieszkania ma więcej powierzchni niż suma min_powierzchni pokoi (typowy przypadek), kto absorbuje nadmiar żeby F1 (100% coverage) było spełnione?

**Opcje:**
- (a) **Salon_aneks** — bo ma najszerszy zakres `procent_powierzchni` (max 45%)
- (b) **Sypialnia główna** — bo druga największa
- (c) **Hub** — ale to łamie F4 (hub max 15%)

**Status:** DECIDED 2026-04-30
**Decyzja Dawida:** salon bierze **80% nadmiaru**, pozostałe **20% rozdzielone proporcjonalnie między sypialnie**. Sypialnie nie muszą siedzieć na minimum — mogą iść powyżej. Hub i pokoje usługowe (łazienka, WC) zostają przy `procent_powierzchni` lub twardym capie WT (Q7). Przykład: mieszkanie 100m², suma min_powierzchni = 60m² → nadmiar 40m² → salon dostaje +32m², sypialnie razem +8m² (proporcjonalnie do swoich min_powierzchnia).

### Q7: 5m² łazienka vs `procent_powierzchni`
**Pytanie:** w `M3_standard.json` łazienka ma `procent_powierzchni: [0.06, 0.12]`. Dla mieszkania 100m² to 6-12m². Konflikt z F2 (max 5m²).

**Opcje:**
- (a) **F2 wins** — `min(procent_powierzchni × usable, 5.0)` jako twardy cap
- (b) **Procent_powierzchni wins** — ale to łamie F2

**Status:** DECIDED 2026-04-30
**Decyzja Dawida:** opcja (a) — **F2 wins**. Twardy cap WT ma pierwszeństwo nad `procent_powierzchni` z szablonu.

**Capy WT (uściślone 2026-04-30):**
- Łazienka: min 2.5m² / opt ~4.5-5.0m² / **max 5.0m²**
- WC: min 1.5m² / **opt 1.8m²** / **max 3.0m²**

Efektywny upper bound: `min(procent_max × usable_area, WT_MAX_AREA[room_id])`. Implementacja: stała `WT_MAX_AREA` w `config.py` + constraint `model.add(area_i <= max_area_cm2)` w solverze + funkcja `_check_max_areas` w validatorze.

### Q8: Klatka schodowa w etapie 4
**Pytanie:** czy etap 4 dostaje sam obrys mieszkania (już bez klatki) czy obrys z klatką do wycięcia?

**Opcje:**
- (a) **Bez klatki** — etap 3 (Floor mode) już wyciął klatkę, etap 4 dostaje czyste mieszkania
- (b) **Z klatką** — etap 4 musi sam wyciąć

**Rekomendacja:** (a) — separation of concerns.

**Status:** OPEN

---

## ETAP 3 — PIĘTRO (gdy będziemy portować z C++)

### Q9: Jak portować Floor mode z C++ do Python
**Pytanie:** Floor mode (etap 3) działa w C++ (6/6 testów). Czy port do Pythona ma być 1:1 czy reimplementacja?

**Opcje:**
- (a) **Port 1:1** — szybciej ale C++ idiomy w Pythonie
- (b) **Reimplementacja** — wolniej ale czysty Pythonic kod (Shapely zamiast geometrii ręcznej)

**Rekomendacja:** (b) — etap 4 też ma być Pythonic, więc jednolity styl.

**Status:** OPEN — decyzja gdy dojdziemy do etapu 3.

---

## OGÓLNE

### Q10: Python Palette w AC vs CLI
**Pytanie:** jak end-user uruchamia FloorPlan6?

**Opcje:**
- (a) **Python Palette w AC** (nadbudowa Tapira) — klika przycisk w AC
- (b) **CLI** — `python main.py` z terminala
- (c) **PyQt5 GUI** (`ui/main_window.py`) — okno desktop

**Rekomendacja:** docelowo **(a)** dla architektów. **(b)+(c)** dla developera. Sprawdzić jak Tapir Python Palette się konfiguruje.

**Status:** OPEN — decyzja przed pierwszym deploymentem do user.

---

## DECYDED (przykład — gdy przeniesiemy odpowiedź)

> Format po decyzji:
> ```
> ### QX: [pytanie]
> **Status:** DECIDED 2026-MM-DD
> **Decyzja:** opcja (a) — uzasadnienie Dawida: ...
> ```

---

## PROCES

1. Claude napotyka decyzję → sprawdza ten plik
2. Jeśli Q jest OPEN → STOP, pyta Dawida
3. Po decyzji Dawida → Claude UPDATE-uje ten plik (przesuwa Q do DECIDED z datą i uzasadnieniem)
4. Claude implementuje zgodnie z decyzją
5. Jeśli implementacja ujawnia nowe pytania → DODAJ jako Q11, Q12, …

**Reguła B5:** pytaj o decyzje architektoniczne, NIE o oczywistości.
