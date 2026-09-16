"""Tryb beta (FLOORFORGE_BETA): jedna zakładka + brak importu zamrożonych etapów."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt5")


def test_beta_mode_single_english_tab(qapp, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    monkeypatch.setenv("FLOORFORGE_VERSION", "beta-test")
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() == 1
    assert w.tabs.tabText(0) == "Room layout"
    assert w.windowTitle() == "FloorForge beta-test"
    assert hasattr(w, "ac_status")
    # Pusty podgląd musi nazywać przyciski tak, jak są podpisane.
    placeholder = w.image_label.text()
    assert w.import_btn.text() in placeholder, placeholder
    assert w.generate_btn.text() in placeholder, placeholder


def test_beta_house_mode_placeholder_uses_real_button_label(qapp, monkeypatch):
    """Po przełączeniu na tryb domu komunikat też cytuje realną etykietę przycisku."""
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    from ui.main_window import MainWindow
    w = MainWindow()
    w.mode_house_radio.setChecked(True)
    txt = w.image_label.text()
    assert "House mode" in txt, txt
    assert w.generate_btn.text() in txt, txt


def test_default_mode_placeholder_uses_real_button_labels(qapp, monkeypatch):
    """Etykiety muszą się zgadzać z przyciskami także w trybie domyślnym."""
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    from ui.main_window import MainWindow
    w = MainWindow()
    txt = w.image_label.text()
    assert w.import_btn.text() in txt, txt
    assert w.generate_btn.text() in txt, txt


def test_default_mode_unchanged(qapp, monkeypatch):
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() >= 2
    assert w.windowTitle() == "FloorPlan6 — Apartment Layout Generator"
    # Pasek statusu AC jest w OBU trybach (dialog AC-offline mówi „click Refresh").
    assert hasattr(w, "ac_status")


def test_beta_labels_survive_button_resets(qapp, monkeypatch):
    """Po resecie wraca DOKŁADNIE ten sam napis, co na starcie."""
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    from ui.main_window import MainWindow
    w = MainWindow()

    assert w.import_btn.text() == "Load outline from Archicad"
    w.import_btn.setText("cokolwiek")
    w._reset_import_button()
    assert w.import_btn.text() == "Load outline from Archicad"

    w._on_error(RuntimeError("x"))
    assert w.generate_btn.text() == "3. Generate layouts"
    assert w.generate_btn.isEnabled()


@pytest.mark.parametrize("beta", [True, False])
def test_user_visible_strings_are_english(qapp, monkeypatch, beta):
    """Beta idzie do testerów spoza Polski: zero polskich znaków w widocznych napisach."""
    if beta:
        monkeypatch.setenv("FLOORFORGE_BETA", "1")
    else:
        monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    from ui.main_window import MainWindow
    w = MainWindow()
    w.mode_house_radio.setChecked(True)

    visible = [
        w.windowTitle(), w.tabs.tabText(w.tabs.indexOf(w.apt_tab)),
        w.import_btn.text(), w.click_pick_btn.text(), w.generate_btn.text(),
        w.export_btn.text(), w.archicad_btn.text(), w.facades_btn.text(),
        w.mode_apartment_radio.text(), w.mode_house_radio.text(),
        w.furniture_check.text(), w.house_both_storeys_check.text(),
        w.house_program_label.text(), w.image_label.text(),
        w.ac_status.label.text(), w.ac_status.refresh_btn.text(),
        w.house_storey_combo.itemText(0), w.house_storey_combo.itemText(1),
    ]
    polish = set("ąćęłńóśźż")
    offenders = [t for t in visible if polish & set(t.lower())]
    assert not offenders, offenders


def test_storey_combo_labels_english_but_keys_unchanged(qapp, monkeypatch):
    """Widoczne napisy po angielsku, klucze kontraktu (`parter`/`poddasze`) bez zmian."""
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    from ui.main_window import MainWindow, STOREY_KEYS
    w = MainWindow()
    assert [w.house_storey_combo.itemText(i) for i in range(2)] == ["Ground floor", "Attic"]
    assert STOREY_KEYS["Ground floor"] == "parter"
    assert STOREY_KEYS["Attic"] == "poddasze"


def test_beta_mode_does_not_import_frozen_stages():
    """Osobny proces: w becie ui.stage1_window / floor_layout_window nie są importowane."""
    code = (
        "import os, sys; os.environ['FLOORFORGE_BETA']='1'; os.environ['QT_QPA_PLATFORM']='offscreen'\n"
        "from PyQt5.QtWidgets import QApplication; app=QApplication([])\n"
        "from ui.main_window import MainWindow; w=MainWindow()\n"
        "bad=[m for m in ('ui.stage1_window','ui.floor_layout_window','ui.stage_placeholder','core.report_pdf') if m in sys.modules]\n"
        "print('BAD=' + ','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": "."})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("BAD="), out.stdout


@pytest.mark.parametrize("beta", [True, False])
def test_left_panel_scrolls_at_minimum_window_size(qapp, monkeypatch, beta):
    """Lewy panel (~1200 px) musi się przewijać przy 1100×700 — inaczej na 13" laptopie
    przyciski eksportu i komunikat AC są zgniecione do kilku pikseli."""
    if beta:
        monkeypatch.setenv("FLOORFORGE_BETA", "1")
    else:
        monkeypatch.delenv("FLOORFORGE_BETA", raising=False)

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QScrollArea
    from ui.main_window import MainWindow

    w = MainWindow()
    w.resize(1100, 700)
    w.show()
    qapp.processEvents()
    qapp.processEvents()
    try:
        # (a) lewy panel siedzi w przewijalnym QScrollArea
        assert isinstance(w.left_scroll, QScrollArea)
        assert w.left_scroll.widgetResizable() is True

        # (b) zawartość jest wyższa niż viewport → przewijanie jest potrzebne i dostępne
        inner = w.left_scroll.widget()
        assert inner is not None
        assert inner.sizeHint().height() > w.left_scroll.viewport().height()

        # (b2) w poziomie NIE przewijamy, więc treść musi mieścić się w viewport —
        # to uzasadnia kolumnę 299 px (280 treści + pasek) zamiast 280 px.
        assert w.left_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert inner.width() <= w.left_scroll.viewport().width()

        # (c) komunikat o statusie ArchiCAD nie jest zgnieciony
        label = w.ac_status.label
        assert label.height() >= label.sizeHint().height()
    finally:
        w.close()
