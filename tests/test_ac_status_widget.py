"""Pasek statusu ArchiCAD w GUI.

Zakres: brak AC / port+projekt+kondygnacja / odporność na wyjątek /
NIE przestawia portu singletona TapirConnection (cel eksportu z pickera).
"""
import pytest

pytest.importorskip("PyQt5")

STORIES = {
    "actStory": 1,
    "firstStory": 0,
    "lastStory": 1,
    "stories": [{"index": 0, "name": "Parter"}, {"index": 1, "name": "Poddasze"}],
}


class _FakeTypes:
    def AddOnCommandId(self, namespace, name):
        return (namespace, name)


class _FakeCommands:
    def __init__(self, result):
        self._result = result

    def ExecuteAddOnCommand(self, command_id, params):
        return self._result


class _FakeConn:
    """Świeże połączenie per port — tak jak zwraca TapirConnection._try_connect()."""

    def __init__(self, result=None):
        self.types = _FakeTypes()
        self.commands = _FakeCommands(STORIES if result is None else result)


def test_status_no_archicad(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: []))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Not connected to Archicad" in w.label.text()
    assert "FloorForge add-on" in w.label.text()     # NIE "Tapir" — tester ma bundle FloorForge
    assert w.instances == []


def test_status_shows_port_project_story(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19723, "projectName": "Dom K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: _FakeConn()))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    t = w.label.text()
    assert t.startswith("Archicad port 19723 ")
    assert "Dom K" in t and "storey Poddasze" in t


def test_status_survives_exception(qapp, monkeypatch):
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: (_ for _ in ()).throw(OSError("boom"))))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()
    assert "Not connected to Archicad" in w.label.text()


def test_refresh_does_not_retarget_singleton(qapp, monkeypatch):
    """Odśwież NIE może przestawić portu singletona — user wybrał cel w pickerze."""
    import bridge.tapir_connection as tc
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: [
        {"port": 19723, "projectName": "Dom K", "projectPath": ""},
        {"port": 19724, "projectName": "Inny", "projectPath": ""},
    ]))
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: _FakeConn()))

    singleton = tc.TapirConnection()
    monkeypatch.setattr(singleton, "_active_port", 19730, raising=False)
    monkeypatch.setattr(singleton, "_conn", "sentinel-conn", raising=False)

    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()

    assert "(+1 more)" in w.label.text()
    assert tc.TapirConnection()._active_port == 19730
    assert tc.TapirConnection()._conn == "sentinel-conn"


def test_refresh_marks_button_busy_and_restores_it(qapp, monkeypatch):
    """Na czas skanu portów przycisk jest nieaktywny („Checking…"), potem wraca — nawet po wyjątku."""
    import bridge.tapir_connection as tc
    seen = {}

    def _during(cls, **k):
        seen["text"] = w.refresh_btn.text()
        seen["enabled"] = w.refresh_btn.isEnabled()
        raise OSError("boom")

    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(_during))
    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()

    assert seen["text"] == "Checking…"
    assert seen["enabled"] is False
    assert w.refresh_btn.text() == "Refresh"
    assert w.refresh_btn.isEnabled()


# ───────────── auto-odświeżanie przy starcie z add-onu (FLOORFORGE_LAUNCHED_FROM_AC) ─────────────
@pytest.mark.parametrize("env", ["FLOORFORGE_LAUNCHED_FROM_AC", "FLOORFORGE_AC_PORT"])
def test_auto_refresh_when_launched_from_archicad(qapp, monkeypatch, env):
    """Start z AC: pasek sam się odświeża po pokazaniu okna — user nie musi klikać „Refresh"."""
    import bridge.tapir_connection as tc
    monkeypatch.setenv(env, "1" if env.endswith("FROM_AC") else "19723")
    monkeypatch.setattr(tc.TapirConnection, "list_instances",
                        classmethod(lambda cls, **k: [{"port": 19723, "projectName": "Dom K", "projectPath": ""}]))
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: _FakeConn()))

    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    assert "not checked" in w.label.text()     # przed pętlą zdarzeń jeszcze nic nie skanowaliśmy
    qapp.processEvents()

    t = w.label.text()
    assert "not checked" not in t
    assert "19723" in t and "Dom K" in t


def test_no_auto_refresh_without_env(qapp, monkeypatch):
    """Zwykły start (z Findera): bez skanu portów przy otwarciu okna."""
    import bridge.tapir_connection as tc
    monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)
    monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)
    called = {"n": 0}

    def _boom(cls, **k):
        called["n"] += 1
        return []

    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(_boom))

    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    qapp.processEvents()

    assert w.label.text() == "Archicad: not checked"
    assert called["n"] == 0


def test_status_strings_have_no_polish_letters():
    """Bramka §9: pasek statusu AC jest w całości po angielsku."""
    from ui import ac_status_widget as m
    polish = set("ąćęłńóśźż")
    for txt in (m.BUSY_TEXT, m.REFRESH_TEXT, m.NO_AC_TEXT, m.NOT_CHECKED_TEXT):
        assert not polish & set(txt.lower()), txt
        assert "tapir" not in txt.lower(), txt


# ───────────── preferencja portu z env (spec §4, I4) ─────────────
def test_status_prefers_instance_named_by_env_port(qapp, monkeypatch):
    """Dwie instancje + FLOORFORGE_AC_PORT = druga → pasek pokazuje DRUGĄ."""
    import bridge.tapir_connection as tc
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: [
        {"port": 19723, "projectName": "Pierwszy", "projectPath": ""},
        {"port": 19724, "projectName": "Drugi", "projectPath": ""},
    ]))
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: _FakeConn()))

    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()

    t = w.label.text()
    assert t.startswith("Archicad port 19724 ")
    assert "Drugi" in t and "(+1 more)" in t
    assert w.instances[0]["port"] == 19724      # picker eksportu dostaje tę samą kolejność


def test_status_keeps_order_when_env_port_not_among_instances(qapp, monkeypatch):
    """Port z env spoza listy (albo brak env) → kolejność bez zmian."""
    import bridge.tapir_connection as tc
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19999")
    monkeypatch.setattr(tc.TapirConnection, "list_instances", classmethod(lambda cls, **k: [
        {"port": 19723, "projectName": "Pierwszy", "projectPath": ""},
        {"port": 19724, "projectName": "Drugi", "projectPath": ""},
    ]))
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: _FakeConn()))

    from ui.ac_status_widget import AcStatusWidget
    w = AcStatusWidget()
    w.refresh()

    assert w.label.text().startswith("Archicad port 19723 ")
    assert w.instances[0]["port"] == 19723
