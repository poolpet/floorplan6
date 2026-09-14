"""Tryb beta (FLOORFORGE_BETA): jedna polska zakładka + brak importu zamrożonych etapów."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt5")


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
