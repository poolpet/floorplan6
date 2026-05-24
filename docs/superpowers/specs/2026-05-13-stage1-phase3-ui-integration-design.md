# Stage 1 Phase 3 — UI Integration (Stage1ReportDialog) Design

> **Status:** READY — sekcje 1-5 zatwierdzone, self-review pass zamknięty
> (2026-05-13 brainstorm + 2026-05-14 doprecyzowania + self-review).
>
> **Następny krok:** invoke `superpowers:writing-plans` żeby wygenerować
> step-by-step implementation plan.
>
> **NIE rozpoczynamy implementacji** dopóki implementation plan nie powstanie.

---

## Scope decisions (z brainstormingu)

| # | Pytanie | Decyzja |
|---|---|---|
| 1 | Scope Phase 3 | **Tylko Stage1ReportDialog**. Multi-persona views → Phase 3.1. macOS CI → Phase 3.2. |
| 2 | Trigger generacji PDF | **Osobny przycisk "Eksport PDF"** po analizie (nie inline w Generate, nie w menu). |
| 3 | Pokrycie trybów | **Tylko Mode A**. Mode B report — Phase 4 (poza scope). |
| 4 | Sync vs async generacja | **Sync z busy state** (button disabled + `Qt.WaitCursor` + `QApplication.processEvents()`). ~1-3s blokady jest OK. |
| 5 | Output handling | **`QFileDialog.getSaveFileName`** z prefilled filename `Raport_<plot_id>_<YYYY-MM-DD>.pdf`. Po zapisie — `QMessageBox` z opcją "Otwórz PDF". |
| 6 | Metadane do raportu | **Mały dialog "Dane raportu"** przed save. Zbiera `plot_id`, `plot_address`, optional `logo_path`. QSettings persistence dla logo. |
| 7 | Placement przycisku | **Pod przyciskiem "Generate"** w lewym panelu Stage1Widget. Początkowo disabled, aktywuje się po udanym Mode A. |

---

## Sekcja 1 — Architektura wysokopoziomowa ✅ APPROVED

```
┌─────────────────────────────────────────────────────────────────────┐
│  UI: ui/stage1_window.py (MODIFIED, ~+60 LOC)                       │
│    + self._mode_a_results: cache (plot, variants, indicators, ver)  │
│    + self.export_pdf_btn: nowy przycisk pod Generate                │
│    + self._on_export_pdf(): trigger handler                         │
│    + cache invalidation w _run_mode_b / _build_plot fail            │
│                                                                     │
│  UI: ui/report_metadata_dialog.py (NEW, ~120 LOC)                   │
│    + ReportMetadataDialog(QDialog): plot_id / address / logo        │
│    + QSettings("FloorPlan6", "Stage1Report") persistence dla logo   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  CORE: core/report_builder.py (NEW, ~80 LOC)                        │
│    + build_report_data(plot, variants, indicators, verification,    │
│                        plot_id, address, logo, ...) → ReportData    │
│    Mapuje wyniki Mode A pipeline na 1 instancję ReportData.         │
│    Wypełnia lukę z docstring report_data.py wspominającego          │
│    "from_pipeline" — fixture buduje ręcznie, my potrzebujemy        │
│    adaptera dla real pipeline data.                                 │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  CORE (istniejące, NIE modyfikujemy — Phase 2 zamknięte):           │
│    core/report_data.py        — ReportData dataclass + compute_hash │
│    core/report_renderer.py    — 3 matplotlib figures                │
│    core/report_pdf.py         — generate_pdf(rd, path) → 9 stron    │
└─────────────────────────────────────────────────────────────────────┘
```

**Reguła:** żadnych zmian w już zmerge'owanym Phase 2 backend. Tylko adapter + UI.

---

## Sekcja 2 — Komponenty ✅ APPROVED (mapowania doprecyzowane 2026-05-14)

### `core/report_builder.py` (NEW)

```python
def build_report_data(
    plot: Plot,                                # core.plot_model.Plot
    variants: list[BuildupVariant],            # MUST be non-empty; ValueError otherwise
    indicators: PlotIndicators,                # WZ/WIZ/PBC actuals
    verification: list[VerificationResult],    # one per WT rule (may be empty)
    *,
    plot_id: str,
    plot_address: str,
    logo_path: Optional[Path] = None,
) -> ReportData:
    """Adapt Mode A pipeline outputs into a single ReportData.

    Raises:
        ValueError: if variants is empty (Mode A bez wariantów = bug w pipeline).
    """
```

**Mapowania (źródło prawdy: `core/report_data.py` + `tests/fixtures/sample_report.py`):**

| Cel `ReportData` | Źródło |
|---|---|
| `plot_id` | argument |
| `plot_address` | argument |
| `plot_area_m2` | `plot.area` (property = `plot.geometry.area`) |
| `plot_perimeter_m` | `plot.perimeter` (property) |
| `plot_polygon_wkt` | `plot.geometry.wkt` |
| `buildable_polygon_wkt` | `plot.buildable_zone.wkt` (jeśli `is not None`, inaczej `""`) |
| `buildable_zone_m2` | `plot.buildable_zone.area` lub `0.0` |
| `buildable_zone_percent` | `buildable_zone_m2 / plot.area * 100` (guard `plot.area > 0`) |
| `mpzp_summary` | `MPZPSummary(przeznaczenie=plot.mpzp.przeznaczenie, wz_max=plot.mpzp.max_wz, wiz_max=plot.mpzp.max_wiz, pbc_min_percent=plot.mpzp.min_pbc_percent, max_height_m=plot.mpzp.max_height, typ_zabudowy=plot.housing_type.value, line_zabudowy_m=plot.mpzp.setback_from_road, infrastructure_municipal=plot.mpzp.infrastructure_municipal)` |
| `setbacks` | `SetbackInfo(front_m=plot.mpzp.setback_from_road, side_m=BOUNDARY_SETBACK[SASIAD_NIEZABUDOWANY][0], rear_m=BOUNDARY_SETBACK[SASIAD_NIEZABUDOWANY][0])` — pierwszy element tuple (with-openings). Heurystyka: bez per-edge orientation side==rear. |
| `indicators` | `[IndicatorRow("WZ", indicators.wz_designed, plot.mpzp.max_wz, "", status), IndicatorRow("WIZ", indicators.wiz_designed, plot.mpzp.max_wiz, "", status), IndicatorRow("PBC", indicators.pbc_percent, plot.mpzp.min_pbc_percent, "%", status)]` |
| `verification_results` | `[ComplianceRow(rule_id, rule_name, designed_value_str, required_value_str, status.value, legal_basis) for v in verification]` |
| `buildup_variants` | `_to_variant_info(v, plot)` per `variants[:3]` |
| `logo_path` | argument (top-level, **nie** w `cover`) |
| `data_hash` | `compute_hash(rd)` na końcu |

**Status logic dla `IndicatorRow` (Q14 5% band):**

```python
def _status(designed, limit, is_min):
    band = limit * 0.05
    if is_min:  # PBC: designed >= limit
        if designed >= limit: return "OK"
        if designed >= limit - band: return "WARN"
        return "VIOLATION"
    else:  # WZ/WIZ: designed <= limit
        if designed <= limit: return "OK"
        if designed <= limit + band: return "WARN"
        return "VIOLATION"
```

**`_to_variant_info(v: BuildupVariant, plot: Plot) -> VariantInfo` mapping:**

| `VariantInfo` field | Source |
|---|---|
| `number` | `v.number` |
| `footprint_area_m2` | `v.footprint_area` |
| `wz` | `v.wz` |
| `wiz` | `v.wiz` |
| `pbc_percent` | `v.pbc_percent` |
| `description` | `v.description` |
| `pum_m2` | `v.main_building.footprint_area * v.main_building.floors * USABLE_AREA_FACTOR` (import from `core.plot_indicators`) |
| `num_storeys` | `v.main_building.floors` |
| `height_m` | `v.main_building.height` |
| `wz_headroom_percent` | `v.wz_headroom_percent` (już policzony przez SitePlanner) |
| `pbc_headroom_percent` | `v.pbc_percent - plot.mpzp.min_pbc_percent` (procent punkty) |
| `parking_spaces` | `sum(1 for e in v.elements if e.element_type == SiteElementType.MIEJSCE_POSTOJOWE)` |
| `estimated_units` | `estimate_units(pum_m2)` |
| `long_description` | `v.description` (reuse krótkiego — decyzja 2026-05-14, brak długich opisów w produkcji do Phase 4) |

### `ui/report_metadata_dialog.py` (NEW)

```python
class ReportMetadataDialog(QDialog):
    """Pre-save dialog collecting plot_id / address / optional logo."""

    def __init__(self, parent=None, default_plot_id: str = ""):
        # Pola:
        #   QLineEdit plot_id_edit   (default_plot_id z argumentu, np. "Działka 2026-05-14")
        #   QLineEdit address_edit   (placeholder "ul. Słoneczna 12, Warszawa")
        #   QPushButton logo_btn ("Wybierz logo…") + QLabel logo_path_lbl
        # QSettings("FloorPlan6", "Stage1Report"):
        #   "last_logo_path" — read on init, write on accept
        # QDialogButtonBox(OK | Cancel)

    def get_metadata(self) -> dict:
        """Returns metadata after Accepted. Caller MUST check exec_() == Accepted first.

        Returns dict with keys: plot_id (str), plot_address (str), logo_path (Path | None).
        """
```

### `ui/stage1_window.py` (MODIFY)

- Atrybut cache w `__init__`: `self._mode_a_results: tuple | None = None`
- Nowy przycisk `self.export_pdf_btn` pod `self.generate_btn` (zielony, 36px, disabled na start)
- W `_run_mode_a` na końcu: zapisz cache, enable button, update tooltip
- W `_run_mode_b` + fail paths: invalidate cache, disable button
- Nowa metoda `_on_export_pdf` — patrz Sekcja 3

---

## Sekcja 3 — Data flow ✅ APPROVED

```
1. User klika [Generate] (Mode A wybrane)
   └─ _run_mode_a(plot)
      ├─ SitePlanner / PlotIndicatorCalculator / PlotVerifier (istniejące)
      ├─ _render_mode_a + _show_mode_a_info (istniejące)
      └─ NEW:
         self._mode_a_results = (plot, variants, indicators, verification)
         self.export_pdf_btn.setEnabled(True)

2. User klika [📄 Eksport raportu PDF]
   └─ _on_export_pdf():
      a) Guard: cache None → QMessageBox.warning, return (defensywne)
      b) today = date.today()
         default_pid = f"Działka {today:%Y-%m-%d}"
         dlg = ReportMetadataDialog(self, default_plot_id=default_pid)
         if dlg.exec_() != QDialog.Accepted: return
         meta = dlg.get_metadata()  # zwraca dict tylko po Accepted
      c) suggested = f"Raport_{meta['plot_id']}_{today:%Y-%m-%d}.pdf"
         suggested = re.sub(r'[^\w\-_. ]', '_', suggested)
         path, _ = QFileDialog.getSaveFileName(self, "Zapisz raport PDF",
                                                suggested, "PDF (*.pdf)")
         if not path: return
      d) BUSY STATE:
         button.setEnabled(False); button.setText("Generuję raport…")
         QApplication.setOverrideCursor(Qt.WaitCursor)
         statusBar.showMessage("Generowanie PDF…")
         QApplication.processEvents()
      e) try:
           plot, variants, indicators, verification = self._mode_a_results
           rd = build_report_data(plot, variants, indicators, verification,
                                  plot_id=meta["plot_id"],
                                  plot_address=meta["plot_address"],
                                  logo_path=meta["logo_path"])
           generate_pdf(rd, path)
         except Exception as e:
           QMessageBox.critical(self, "Błąd generacji",
                                f"Nie udało się wygenerować PDF:\n{e}")
           return
         finally:
           QApplication.restoreOverrideCursor()
           button.setEnabled(True); button.setText("📄 Eksport raportu PDF")
      f) Success:
         statusBar.showMessage(f"Raport zapisany: {path}")
         resp = QMessageBox.information(self, "Raport gotowy",
             f"PDF zapisany:\n{path}",
             QMessageBox.Open | QMessageBox.Ok)
         if resp == QMessageBox.Open:
             QDesktopServices.openUrl(QUrl.fromLocalFile(path))
```

**Cache invalidation:** po każdym `_run_mode_b`, każdym fail w `_build_plot`, oraz po toggle radio housing_type. Zapobiega PDF z desync params.

**Świadomie POMINIĘTE (YAGNI):**
- Re-run Mode A przy kliknięciu Eksport (user widzi to co w canvas)
- Dirty-state detection (params changed since Generate)
- Multi-PDF batch

---

## Sekcja 4 — Error handling ✅ APPROVED

| # | Scenariusz | Reakcja |
|---|---|---|
| E1 | `_mode_a_results is None` przy kliku | `QMessageBox.warning` + return (defensywne; button zwykle disabled). |
| E2 | Cancel w ReportMetadataDialog | Cichy return. |
| E3 | Cancel w QFileDialog | Cichy return. |
| E4 | `build_report_data` exception | try/except → `QMessageBox.critical("Błąd przygotowania danych raportu:\n{e}")`. Cursor restored, button re-enabled. |
| E5 | `generate_pdf` exception | Ten sam try/except. `"Nie udało się wygenerować PDF:\n{e}"`. |
| E6 | File write fails (permissions / dysk / unicode path) | Łapane w try/except. Path w komunikacie. |
| E7 | Logo file usunięte/uszkodzone | Już guard w `report_pdf.py:cover_page` — pomija logo bez komunikatu. |
| E8 | Brakujący Polish font (Linux/Windows) | Już fallback do Helvetica w `report_pdf.py:40-50`. Diakrytyki mogą uszkodzone — adresuje Phase 3.2 (macOS CI). |
| E9 | Race condition (klik podczas Mode A) | Niemożliwe — Mode A sync, button disabled aż skończy. |

**Logging:** brak — wszystkie błędy do `QMessageBox`. Można dodać `logging.exception` jeśli zaczną się powtarzać. YAGNI.

---

## Sekcja 5 — Testing strategy ✅ APPROVED (2026-05-14)

> Doprecyzowania z sesji 2026-05-14 wpisane poniżej.

### `tests/test_report_builder.py` (~160 LOC, 9 testów)

- `test_build_report_data_from_minimal_pipeline()` — happy path, asserts pól ReportData
- `test_indicator_status_OK_WARN_VIOLATION()` — Q14 5% band
- `test_variant_info_headroom_computed()` — wz_headroom, pbc_headroom, estimated_units
- `test_compliance_status_mapping()` — VerificationStatus → string
- `test_logo_path_None_does_not_crash()` — adapter akceptuje `logo_path=None`
- `test_logo_path_None_propagates()` — `rd.logo_path is None` przy `logo_path=None` (top-level w `ReportData`)
- `test_hash_stable_for_same_inputs()` — determinism (compute_hash idempotent)
- `test_empty_variants_raises_valueerror()` — `build_report_data(..., variants=[])` → `ValueError("variants must be non-empty")`
- `test_polish_chars_preserved()` — ąęćźż w plot_address propagują do `rd.plot_address`

### `tests/test_report_metadata_dialog.py` (~100 LOC, 5 testów)

> **QApplication fixture:** session-scoped `qapp` w `tests/conftest.py` (ręcznie:
> `QApplication.instance() or QApplication([])`). Bez `pytest-qt` jako zależności.
> **QSettings isolation:** monkeypatch `QSettings` defaults na `IniFormat` +
> `setPath(UserScope, tmp_path)` w fixture `isolated_qsettings`. Bez tej izolacji
> testy zatruwałyby `~/.config/FloorPlan6/Stage1Report.conf` użytkownika.

- `test_dialog_default_plot_id_is_today()` — placeholder = `f"Działka {date.today():%Y-%m-%d}"`
- `test_dialog_accept_returns_metadata_dict()` — keys: `plot_id`, `plot_address`, `logo_path`
- `test_dialog_cancel_returns_rejected()` — Cancel → `dlg.exec_()` zwraca `QDialog.Rejected`; `get_metadata()` nigdy nie jest wołane
- `test_logo_picker_updates_label()` — symuluj wybór → label pokazuje basename
- `test_qsettings_remembers_last_logo()` — pierwszy dialog zapisuje, drugi czyta (z `isolated_qsettings`)

### Nie robimy

- E2E Mode A → PDF — pokryte przez `tests/test_report_pdf.py` z fixture (Phase 2)
- `_on_export_pdf` integration test — mockowanie QFileDialog/QMessageBox kruche; manualne smoke wystarczy
- Test sanitization filename (regex `[^\w\-_. ]` → `_`) — `\w` Unicode matchuje `ąęćźż`, jednolinijka, manual smoke
- `tests/test_gui.py` rozszerzenie — i tak crashuje headless

### Manual verification (B8 — verify before "done")

1. `pytest tests/test_report_builder.py -v` → green
2. `pytest tests/test_report_metadata_dialog.py -v` → green (lokalnie; headless może skip)
3. `pytest tests/ --ignore=tests/test_gui.py -q` → suite green (baseline 196 + ~14 nowych)
4. `PYTHONPATH=. python ui/stage1_window.py`:
   - Generate Mode A → przycisk eksport aktywuje się
   - Klik Eksport → dialog metadanych → wypełnij polskie znaki (`ąęćźż`) w adresie → OK → QFileDialog → save
   - Filename: sprawdź że polskie znaki w `plot_id` przechodzą (lub są sanitizowane do `_`)
   - Otwórz PDF → 9 stron + Polish chars OK
   - Klik Eksport po Mode B → disabled z tooltipem
   - Zmień WZ bez Generate → cache desync → świadomy trade-off

---

## Open items

1. ~~**Sekcja 5 confirm**~~ — ✅ closed 2026-05-14
2. ~~**Spec self-review loop**~~ — ✅ closed 2026-05-14 (8 niespójności fields/cover/cancel naprawione, 2 decyzje: long_description=reuse, setbacks=mpzp+WT)
3. **`writing-plans` invoke** — wygeneruj step-by-step implementation plan z checkboxami
4. **Implementacja** — TDD per `writing-plans` output
