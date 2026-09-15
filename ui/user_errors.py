"""Wyjątek → (tytuł, treść) po polsku. Jedno zdanie przyczyny + jedno zdanie porady.
Testowalne bez Qt."""
from __future__ import annotations

import os

from ui.app_logging import log_path

_AC_PORTS = "19723–19730"
_REPR_LIMIT = 200


def _tail(exc: BaseException) -> str:
    r = repr(exc)
    if len(r) > _REPR_LIMIT:
        r = r[:_REPR_LIMIT - 3] + "..."
    lp = log_path()
    log_line = f"\n\nLog: {lp}" if lp else ""
    return f"{log_line}\n\nSzczegóły techniczne: {r}"


def describe(exc: BaseException) -> tuple[str, str]:
    """Zwraca (tytuł okna, treść) po polsku dla dowolnego wyjątku."""
    msg = str(exc)
    low = msg.lower()

    if isinstance(exc, (ConnectionRefusedError, ConnectionError)) or "connection refused" in low \
            or "nie znaleziono archicad" in low:
        if os.environ.get("FLOORFORGE_LAUNCHED_FROM_AC") == "1":
            return ("ArchiCAD",
                    "Uruchomiono z ArchiCADa, ale AC nie odpowiada na porcie JSON. "
                    "Sprawdź Opcje → Ustawienia → JSON API (port 19723) i kliknij Odśwież." + _tail(exc))
        return ("ArchiCAD",
                f"Nie znaleziono ArchiCADa na portach {_AC_PORTS}. "
                "Uruchom AC z załadowanym dodatkiem Tapir i kliknij Odśwież." + _tail(exc))
    if isinstance(exc, TimeoutError) or "timed out" in low:
        return ("ArchiCAD",
                "ArchiCAD nie odpowiada. Zamknij otwarte okna dialogowe w AC i spróbuj ponownie." + _tail(exc))
    if (isinstance(exc, KeyError) and "librarypart" in low) or "additionalproperties" in low:
        return ("Dodatek Tapir",
                "Dodatek Tapir w AC nie obsługuje wymaganych parametrów (np. libraryPart w CreateDoors). "
                "Zainstaluj bundle z paczki FloorForge." + _tail(exc))
    if "infeasible" in low or "nie znaleziono układu" in low or low == "unknown":
        return ("Brak układu",
                "Nie znaleziono układu dla tego obrysu i typu. "
                "Spróbuj inny typ lub powiększ obrys." + _tail(exc))
    if isinstance(exc, ValueError):
        return ("Dane wejściowe", f"{msg} Popraw dane i spróbuj ponownie." + _tail(exc))
    return ("Nieoczekiwany błąd",
            "Coś poszło nie tak. Prześlij plik logu autorowi aplikacji." + _tail(exc))
