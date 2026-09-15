import pytest

from bridge.tapir_connection import TapirConnection


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Class-state singletona nie wycieka między testami — ani DO tego pliku, ani z niego.

    Bez tego zatruty singleton (_conn="scan-conn" z zamockowanego _scan_for_archicad)
    przechodzi do innych plików testowych i przewraca je zależnie od kolejności.
    """
    TapirConnection._instance = None
    TapirConnection._conn = None
    TapirConnection._active_port = None
    yield
    TapirConnection._instance = None
    TapirConnection._conn = None
    TapirConnection._active_port = None


def _conn(monkeypatch):
    import bridge.tapir_connection as tc
    tc.TapirConnection._instance = None          # świeży singleton
    c = tc.TapirConnection()
    calls = {"use_port": [], "scan": 0}
    monkeypatch.setattr(tc.TapirConnection, "_scan_for_archicad",
                        lambda self: (calls.__setitem__("scan", calls["scan"] + 1) or (19725, "scan-conn")))
    return tc, c, calls


def test_env_port_alive_is_used_without_scan(monkeypatch):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: "conn-19724" if port == 19724 else None))
    assert c.connect() is True
    assert c.active_port == 19724 and c._conn == "conn-19724"
    assert calls["scan"] == 0


def test_env_port_dead_falls_back_to_scan(monkeypatch, caplog):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19724")
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert c.active_port == 19725 and calls["scan"] == 1
    assert any("FLOORFORGE_AC_PORT" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad", ["", "abc", "0", "70000"])
def test_env_port_invalid_falls_back_to_scan(monkeypatch, bad):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.setenv("FLOORFORGE_AC_PORT", bad)
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert calls["scan"] == 1


def test_no_env_keeps_scan_behaviour(monkeypatch):
    tc, c, calls = _conn(monkeypatch)
    monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)
    monkeypatch.setattr(tc.TapirConnection, "_try_connect", staticmethod(lambda port: None))
    assert c.connect() is True
    assert calls["scan"] == 1
