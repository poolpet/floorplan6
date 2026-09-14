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


# ─────────────────── story_navitems / activate_story (auto-switch) ───────────
class _FakeNav:
    """Minimalny obiekt drzewa nawigatora: StoryItem'y top-down (Poddasze, Parter)."""
    def __init__(self, guids_top_down):
        self.rootItem = self
        self.type = "Root"
        self.navigatorItemId = None
        self.children = [
            type("N", (), {"navigatorItem": type("I", (), {
                "type": "StoryItem",
                "navigatorItemId": type("G", (), {"guid": g})(),
                "children": [],
            })()})()
            for g in guids_top_down
        ]


def _conn_with_stories(monkeypatch, act_story_seq, first=0,
                       guids_top_down=("guid-poddasze", "guid-parter")):
    """TapirConnection z podmienionym połączeniem: GetStories zwraca kolejne actStory z listy.

    `first` = `GetStories.firstStory` (przy piwnicy bywa ujemne), `guids_top_down` =
    StoryItemy w kolejności ProjectMap (od góry).
    """
    conn = tc.TapirConnection()
    calls = {"change_window": []}
    seq = list(act_story_seq)
    last = first + len(guids_top_down) - 1

    class _Cmds:
        def GetNavigatorItemTree(self, tid):
            return _FakeNav(list(guids_top_down))

        def ExecuteAddOnCommand(self, cid, params):
            name = cid.name if hasattr(cid, "name") else str(cid)
            if "GetStories" in name:
                return {"actStory": seq[0] if len(seq) == 1 else seq.pop(0),
                        "firstStory": first, "lastStory": last}
            if "ChangeWindow" in name:
                calls["change_window"].append(params)
                return {}
            return {}

    class _Types:
        def NavigatorTreeId(self, type):
            return ("tree", type)

        def AddOnCommandId(self, ns, name):
            return type("Cid", (), {"name": name})()

    monkeypatch.setattr(conn, "_conn",
                        type("C", (), {"commands": _Cmds(), "types": _Types()})(),
                        raising=False)
    return conn, calls


def test_story_navitems_maps_index_to_guid_bottom_up(monkeypatch):
    conn, _ = _conn_with_stories(monkeypatch, [0])
    assert conn.story_navitems() == {0: "guid-parter", 1: "guid-poddasze"}


def test_activate_story_true_when_act_story_changes(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [0, 1])   # przed: 0, po ChangeWindow: 1
    assert conn.activate_story(1) is True
    assert calls["change_window"], "ChangeWindow powinno być wywołane"
    assert calls["change_window"][0]["navigatorItemId"]["guid"] == "guid-poddasze"


def test_activate_story_false_when_no_shape_switches(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [0])      # actStory nigdy się nie zmienia
    assert conn.activate_story(1) is False
    assert len(calls["change_window"]) == len(conn.CHANGE_WINDOW_SHAPES)


def test_activate_story_noop_when_already_active(monkeypatch):
    conn, calls = _conn_with_stories(monkeypatch, [1])
    assert conn.activate_story(1) is True
    assert calls["change_window"] == []


def test_story_navitems_keys_in_ac_index_space_with_basement(monkeypatch):
    """Piwnica (firstStory=-1) → klucze -1/0/1, NIE 0/1/2 (te same indeksy co actStory)."""
    conn, _ = _conn_with_stories(
        monkeypatch, [0], first=-1,
        guids_top_down=("guid-poddasze", "guid-parter", "guid-piwnica"))
    assert conn.story_navitems() == {-1: "guid-piwnica", 0: "guid-parter", 1: "guid-poddasze"}


def test_activate_story_targets_parter_guid_when_basement_shifts_indices(monkeypatch):
    """Z piwnicą activate_story(0) musi trafić w PARTER, nie w kondygnację wyżej."""
    conn, calls = _conn_with_stories(
        monkeypatch, [1, 0], first=-1,
        guids_top_down=("guid-poddasze", "guid-parter", "guid-piwnica"))
    assert conn.activate_story(0) is True
    assert calls["change_window"][0]["navigatorItemId"]["guid"] == "guid-parter"
