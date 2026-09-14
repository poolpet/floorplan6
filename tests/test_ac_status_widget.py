"""Pasek statusu ArchiCAD w GUI: brak AC / port+projekt+kondygnacja / odporność na wyjątek."""
import pytest

pytest.importorskip("PyQt5")


def test_status_no_archicad(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: []))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Brak połączenia" in w.label.text()
    assert w.instances == []


def test_status_shows_port_project_story(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19723, "projectName": "Dom K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "use_port", lambda self, p: True)
    monkeypatch.setattr(tc.TapirConnection, "get_stories",
                        lambda self: {"actStory": 1, "firstStory": 0, "lastStory": 1,
                                      "stories": [{"index": 0, "name": "Parter"}, {"index": 1, "name": "Poddasze"}]})
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    t = w.label.text()
    assert "19723" in t and "Dom K" in t and "Poddasze" in t


def test_status_survives_exception(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: (_ for _ in ()).throw(OSError("boom"))))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Brak połączenia" in w.label.text()
