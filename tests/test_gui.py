"""Smoke tests for GUI — verify MainWindow creates and GenerateWorker runs."""
import sys
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Singleton QApplication — wymagane przez PyQt5
app = QApplication.instance() or QApplication(sys.argv)


def test_main_window_creates():
    """MainWindow creates without errors."""
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.windowTitle() == "FloorPlan6 — Apartment Layout Generator"
    assert w.type_combo.count() == 5
    assert w.width_spin.value() == 8.0


def test_main_window_widgets():
    """Kluczowe widgety istnieją."""
    from ui.main_window import MainWindow
    w = MainWindow()
    assert hasattr(w, 'notch_group')
    assert hasattr(w, 'archicad_btn')
    assert hasattr(w, 'import_btn')
    assert hasattr(w, 'export_btn')
    assert hasattr(w, 'details')
    assert hasattr(w, 'image_label')


def test_generate_worker():
    """GenerateWorker generuje warianty (wywołanie synchroniczne run())."""
    from ui.main_window import GenerateWorker
    from shapely.geometry import Polygon

    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    worker = GenerateWorker(poly, (4.0, 0.0), "M2", 2)

    results = []
    worker.finished.connect(results.append)
    # Wywołaj run() synchronicznie (bez start(), żeby signal dotarł)
    worker.run()

    assert len(results) == 1
    variants = results[0]
    assert len(variants) >= 1
    assert variants[0].score > 0
