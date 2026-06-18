"""GUI: przycisk 'Wstaw do AC' w trybie dom dyspozytoruje do export_house_to_archicad
z wybraną kondygnacją (bez AC — szpieg)."""
import pytest

pytest.importorskip("PyQt5")


def test_house_export_dispatches_selected_storey(qapp, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    import bridge.house_writer as hw
    from ui.main_window import MainWindow

    captured = {}
    monkeypatch.setattr(
        hw, "export_house_to_archicad",
        lambda layout, storey="parter", **kw: (captured.update(storey=storey),
                                               {"zones": [], "walls": [], "doors": [],
                                                "labels": [], "windows": []})[1],
    )
    # nie pokazuj modali w teście
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    w = MainWindow()
    w._archicad_offset = (0.0, 0.0)
    w.mode_house_radio.setChecked(True)          # tryb dom
    w._house_layout = object()                   # truthy „wygenerowany dom"
    w.house_storey_combo.setCurrentText("Poddasze")
    w._export_to_archicad()                       # przycisk „Wstaw do AC"
    assert captured.get("storey") == "poddasze"
