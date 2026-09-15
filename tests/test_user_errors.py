"""Mapowanie wyjątków na polskie komunikaty dla użytkownika (bez Qt)."""
import pytest


@pytest.mark.parametrize("exc, expect_title, expect_frag", [
    (ConnectionRefusedError("[Errno 61] Connection refused"), "ArchiCAD", "Uruchom AC"),
    (ConnectionError("Nie znaleziono ArchiCADa"), "ArchiCAD", "Uruchom AC"),
    (TimeoutError("timed out"), "ArchiCAD", "nie odpowiada"),
    (RuntimeError("INFEASIBLE"), "Brak układu", "Spróbuj inny typ"),
    (ValueError("Obrys musi mieć co najmniej 3 punkty"), "Dane wejściowe", "co najmniej 3 punkty"),
    (KeyError("libraryPart"), "Dodatek Tapir", "Zainstaluj bundle z paczki FloorForge"),
    (ZeroDivisionError("x"), "Nieoczekiwany błąd", "Szczegóły techniczne"),
])
def test_describe_maps_to_polish(exc, expect_title, expect_frag):
    from ui.user_errors import describe
    title, text = describe(exc)
    assert title == expect_title
    assert expect_frag in text
    assert "Szczegóły techniczne:" in text


def test_describe_truncates_long_repr():
    from ui.user_errors import describe
    _, text = describe(RuntimeError("x" * 1000))
    assert len(text.split("Szczegóły techniczne:")[1]) < 260


def test_connection_error_when_launched_from_ac_mentions_json_api(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.setenv("FLOORFORGE_LAUNCHED_FROM_AC", "1")
    title, text = describe(ConnectionError("brak"))
    assert title == "ArchiCAD"
    assert "JSON API" in text and "Odśwież" in text


def test_connection_error_default_wording_without_env(monkeypatch):
    from ui.user_errors import describe
    monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)
    _, text = describe(ConnectionError("brak"))
    assert "Uruchom AC" in text
