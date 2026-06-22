"""AC-targeting: wybór instancji (picker source), story API, guard (czysta logika).

Wszystko offline — `ACConnection`/`_execute_tapir` mockowane. Bez żywego ArchiCAD.
"""
import pytest

import bridge.tapir_connection as tc
from bridge.tapir_connection import TapirConnection, check_active_story


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Class-state singletona nie wycieka między testami."""
    TapirConnection._instance = None
    TapirConnection._conn = None
    TapirConnection._active_port = None
    yield
    TapirConnection._instance = None
    TapirConnection._conn = None
    TapirConnection._active_port = None


# ───────────────────── check_active_story (pure, bez AC) ─────────────────────
@pytest.mark.parametrize("act,first,last,gui,ok", [
    (0, 0, 2, "parter", True),      # parter na story bazowej
    (1, 0, 2, "parter", False),     # parter, ale aktywne piętro
    (1, 0, 2, "poddasze", True),    # poddasze na piętrze
    (2, 0, 2, "poddasze", True),    # poddasze na wyższym piętrze też OK
    (0, 0, 2, "poddasze", False),   # poddasze, ale aktywny parter
    (0, 0, 0, "poddasze", False),   # projekt 1-kondygnacyjny → brak poddasza
    (0, 0, 0, "parter", True),      # parterowiec OK
])
def test_check_active_story(act, first, last, gui, ok):
    res, msg = check_active_story(act, first, last, gui)
    assert res is ok
    assert (msg == "") is ok          # komunikat tylko gdy mismatch


# ───────────────────────────── list_instances ───────────────────────────────
class _FakeConn:
    """Minimalny stub ACConnection — GetProjectInfo zwraca nazwę."""
    def __init__(self, name):
        self._name = name

    class _Types:
        def AddOnCommandId(self, ns, cmd):
            return (ns, cmd)

    class _Cmds:
        def __init__(self, name):
            self._name = name

        def ExecuteAddOnCommand(self, cid, params):
            return {"projectName": self._name, "projectPath": f"/p/{self._name}.pln"}

    @property
    def types(self):
        return self._Types()

    @property
    def commands(self):
        return self._Cmds(self._name)


def test_list_instances_returns_port_and_name(monkeypatch):
    mapping = {19723: _FakeConn("test"), 19724: _FakeConn("Kamienica")}
    monkeypatch.setattr(tc.ACConnection, "connect", staticmethod(lambda port: mapping.get(port)))
    out = TapirConnection.list_instances()
    by_port = {d["port"]: d["projectName"] for d in out}
    assert by_port == {19723: "test", 19724: "Kamienica"}


def test_list_instances_unknown_name_when_projectinfo_fails(monkeypatch):
    class _Boom(_FakeConn):
        class _Cmds:
            def __init__(self, name):
                pass

            def ExecuteAddOnCommand(self, cid, params):
                raise RuntimeError("Tapir bez GetProjectInfo")

        @property
        def commands(self):
            return self._Cmds(self._name)

    monkeypatch.setattr(tc.ACConnection, "connect",
                        staticmethod(lambda port: _Boom("x") if port == 19723 else None))
    out = TapirConnection.list_instances()
    assert out == [{"port": 19723, "projectName": "(nieznany)", "projectPath": ""}]


# ─────────────────────────────── use_port ───────────────────────────────────
def test_use_port_pins_explicit_port(monkeypatch):
    seen = {}

    def fake_connect(port):
        seen["port"] = port
        return _FakeConn("x")

    monkeypatch.setattr(tc.ACConnection, "connect", staticmethod(fake_connect))
    t = TapirConnection()
    assert t.use_port(19724) is True
    assert t.active_port == 19724
    assert seen["port"] == 19724


def test_use_port_raises_when_dead(monkeypatch):
    monkeypatch.setattr(tc.ACConnection, "connect", staticmethod(lambda port: None))
    with pytest.raises(ConnectionError):
        TapirConnection().use_port(19999)


# ──────────────────── get_stories / get_project_info ─────────────────────────
def test_get_stories_passthrough(monkeypatch):
    t = TapirConnection()
    monkeypatch.setattr(t, "_execute_tapir",
                        lambda cmd, params=None: {"actStory": 1, "firstStory": 0} if cmd == "GetStories" else {})
    assert t.get_stories()["actStory"] == 1


def test_get_project_info_passthrough(monkeypatch):
    t = TapirConnection()
    monkeypatch.setattr(t, "_execute_tapir",
                        lambda cmd, params=None: {"projectName": "K"} if cmd == "GetProjectInfo" else {})
    assert t.get_project_info()["projectName"] == "K"
