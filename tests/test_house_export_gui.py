"""GUI: 'Wstaw do AC' w trybie dom — picker instancji + story-guard + dyspozytor kondygnacji.

Bez żywego AC: list_instances/use_port/get_stories/export = szpiedzy (monkeypatch).
"""
import pytest

pytest.importorskip("PyQt5")


def _wire(monkeypatch, *, instances, act_story, first=0, last=2):
    """Wspólny montaż szpiegów. Zwraca dict `cap` z przechwyconymi wywołaniami."""
    from PyQt5.QtWidgets import QMessageBox
    import bridge.tapir_connection as tc
    import bridge.house_writer as hw

    cap = {"export": 0}
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: instances))
    monkeypatch.setattr(tc.TapirConnection, "use_port",
                        lambda self, p: cap.__setitem__("port", p) or True)
    monkeypatch.setattr(tc.TapirConnection, "get_stories",
                        lambda self: {"actStory": act_story, "firstStory": first, "lastStory": last})

    def fake_export(layout, storey="parter", **kw):
        cap["export"] += 1
        cap["storey"] = storey
        cap["has_tapir"] = kw.get("tapir") is not None
        return {"zones": [], "walls": [], "doors": [], "labels": [], "windows": []}

    monkeypatch.setattr(hw, "export_house_to_archicad", fake_export)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    return cap


def _mainwindow(monkeypatch, storey_text):
    from ui.main_window import MainWindow
    w = MainWindow()
    w._archicad_offset = (0.0, 0.0)
    w.mode_house_radio.setChecked(True)
    w._house_layout = object()
    w.house_storey_combo.setCurrentText(storey_text)
    return w


def test_house_export_single_instance_dispatches(qapp, monkeypatch):
    """1 instancja + aktywna story zgodna (poddasze na idx1) → eksport z wybranym tapir+storey."""
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=1)
    w = _mainwindow(monkeypatch, "Poddasze")
    w._export_to_archicad()
    assert cap["export"] == 1
    assert cap["storey"] == "poddasze"
    assert cap["port"] == 19724
    assert cap["has_tapir"] is True


def test_house_export_guard_blocks_storey_mismatch(qapp, monkeypatch):
    """GUI='Poddasze' a aktywna story=parter (idx0) → guard blokuje (user Anuluj), eksport NIE leci."""
    from PyQt5.QtWidgets import QMessageBox
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Cancel))
    w = _mainwindow(monkeypatch, "Poddasze")
    w._export_to_archicad()
    assert cap["export"] == 0


def test_house_export_guard_override_proceeds(qapp, monkeypatch):
    """Mismatch ale user 'Wstaw mimo to' (Yes) → eksport jednak leci."""
    from PyQt5.QtWidgets import QMessageBox
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Yes))
    w = _mainwindow(monkeypatch, "Poddasze")
    w._export_to_archicad()
    assert cap["export"] == 1


def test_house_export_picker_when_multi_instance(qapp, monkeypatch):
    """>1 instancja → picker; wybrany port idzie do use_port + eksportu."""
    from PyQt5.QtWidgets import QInputDialog
    cap = _wire(monkeypatch,
                instances=[{"port": 19723, "projectName": "test", "projectPath": ""},
                           {"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    # picker zwraca drugą pozycję ("19724 — K")
    monkeypatch.setattr(QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: ("19724 — K", True)))
    w = _mainwindow(monkeypatch, "Parter")
    w._export_to_archicad()
    assert cap["export"] == 1
    assert cap["port"] == 19724


def test_house_export_no_instance_warns_no_export(qapp, monkeypatch):
    """0 instancji → ostrzeżenie, brak eksportu."""
    from PyQt5.QtWidgets import QMessageBox
    cap = _wire(monkeypatch, instances=[], act_story=0)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    w = _mainwindow(monkeypatch, "Parter")
    w._export_to_archicad()
    assert cap["export"] == 0


def test_house_export_both_storeys_switches_and_exports_twice(qapp, monkeypatch):
    """Checkbox 'obie' → activate_story(0)+export parter, activate_story(1)+export poddasze."""
    import bridge.tapir_connection as tc
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    switched = []
    monkeypatch.setattr(tc.TapirConnection, "activate_story",
                        lambda self, i: switched.append(i) or True)
    w = _mainwindow(monkeypatch, "Parter")
    w._house_layout = type("L", (), {"pietro_rooms": [object()]})()   # 2-kond.
    w.house_both_storeys_check.setChecked(True)
    w._export_to_archicad()
    assert switched == [0, 1]
    assert cap["export"] == 2


def test_house_export_both_storeys_falls_back_to_guard_when_switch_fails(qapp, monkeypatch):
    """activate_story False → NIE eksportuje na ślepo; pokazuje ostrzeżenie."""
    from PyQt5.QtWidgets import QMessageBox
    import bridge.tapir_connection as tc
    cap = _wire(monkeypatch,
                instances=[{"port": 19724, "projectName": "K", "projectPath": ""}],
                act_story=0)
    monkeypatch.setattr(tc.TapirConnection, "activate_story", lambda self, i: False)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a) or QMessageBox.Cancel))
    w = _mainwindow(monkeypatch, "Parter")
    w._house_layout = type("L", (), {"pietro_rooms": [object()]})()
    w.house_both_storeys_check.setChecked(True)
    w._export_to_archicad()
    assert cap["export"] == 0
    assert warned
