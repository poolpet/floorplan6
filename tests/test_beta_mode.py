"""Tryb beta (FLOORFORGE_BETA): jedna polska zakładka + brak importu zamrożonych etapów."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt5")

# Testy GUI muszą działać bez ekranu (CI / sesja ssh).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_beta_mode_single_polish_tab(qapp, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    monkeypatch.setenv("FLOORFORGE_VERSION", "beta-test")
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() == 1
    assert w.tabs.tabText(0) == "Podział rzutu"
    assert w.windowTitle() == "FloorForge beta-test"
    assert hasattr(w, "ac_status")


def test_default_mode_unchanged(qapp, monkeypatch):
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() >= 2
    assert w.windowTitle() == "FloorPlan6 — Apartment Layout Generator"
    # Pasek statusu AC jest w OBU trybach (dialog AC-offline mówi „kliknij Odśwież").
    assert hasattr(w, "ac_status")


def test_beta_labels_survive_button_resets(qapp, monkeypatch):
    """Etykiety wracają po polsku — resety przycisków nie mogą wstawiać angielskiego."""
    monkeypatch.setenv("FLOORFORGE_BETA", "1")
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    from ui.main_window import MainWindow
    w = MainWindow()

    assert w.import_btn.text() == "Wczytaj obrys z ArchiCAD"
    w.import_btn.setText("cokolwiek")
    w._reset_import_button()
    assert w.import_btn.text() == "Wczytaj obrys z ArchiCAD"

    w._on_error(RuntimeError("x"))
    assert w.generate_btn.text() == "3. Generuj układy"
    assert w.generate_btn.isEnabled()


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

        # (c) komunikat o statusie ArchiCAD nie jest zgnieciony
        label = w.ac_status.label
        assert label.height() >= label.sizeHint().height()
    finally:
        w.close()
