"""Mapowanie wyjątków na angielskie komunikaty dla użytkownika (bez Qt)."""
import pytest


@pytest.mark.parametrize("exc, expect_title, expect_frag", [
    (ConnectionRefusedError("[Errno 61] Connection refused"), "Archicad", "Start Archicad"),
    (ConnectionError("Nie znaleziono ArchiCADa"), "Archicad", "Start Archicad"),
    (TimeoutError("timed out"), "Archicad", "is not responding"),
    (RuntimeError("INFEASIBLE"), "No layout", "Try another type"),
    (ValueError("The outline needs at least 3 points"), "Input data", "at least 3 points"),
    (KeyError("libraryPart"), "FloorForge add-on", "Install the bundle from the FloorForge package"),
    (ZeroDivisionError("x"), "Unexpected error", "Technical details"),
])
def test_describe_maps_to_english(exc, expect_title, expect_frag):
    from ui.user_errors import describe
    title, text = describe(exc)
    assert title == expect_title
    assert expect_frag in text
    assert "Technical details:" in text


def test_describe_has_no_polish_letters():
    """Beta idzie do testerów spoza Polski — zero polskich znaków w treści dla usera."""
    from ui.user_errors import describe
    for exc in (ConnectionRefusedError("x"), TimeoutError("timed out"),
                RuntimeError("INFEASIBLE"), KeyError("libraryPart"), ZeroDivisionError("x")):
        title, text = describe(exc)
        assert not set("\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c") & set((title + text).lower()), text


def test_describe_truncates_long_repr():
    from ui.user_errors import describe
    _, text = describe(RuntimeError("x" * 1000))
    assert len(text.split("Technical details:")[1]) < 260


def test_connection_error_when_launched_from_ac_mentions_json_api(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.setenv("FLOORFORGE_LAUNCHED_FROM_AC", "1")
    monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)
    title, text = describe(ConnectionError("brak"))
    assert title == "Archicad"
    assert "JSON API" in text and "Refresh" in text
    assert "19723" in text                      # domyślny port, gdy env go nie podaje


def test_connection_error_from_ac_uses_port_from_env(monkeypatch):
    """Port w komunikacie musi być TEN, na którym add-on wystawił JSON API."""
    from ui.user_errors import describe
    monkeypatch.setenv("FLOORFORGE_LAUNCHED_FROM_AC", "1")
    monkeypatch.setenv("FLOORFORGE_AC_PORT", "19725")
    _, text = describe(ConnectionError("brak"))
    assert "port 19725" in text


def test_connection_error_default_wording_without_env(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)
    _, text = describe(ConnectionError("brak"))
    assert "Start Archicad" in text


def test_addon_error_never_says_tapir():
    """Tester dostaje bundle FloorForge — nazwa 'Tapir' nic mu nie mówi."""
    from ui.user_errors import describe
    for exc in (KeyError("libraryPart"), ConnectionRefusedError("x")):
        title, text = describe(exc)
        assert "tapir" not in (title + text).lower()
