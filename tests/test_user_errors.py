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
