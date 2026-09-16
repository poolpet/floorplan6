"""Exception -> (title, body) in English. One sentence of cause + one of advice.

Zero Qt, zero UI: serwis HTTP (bez okna) i GUI korzystają z tej samej mapy.
`ui/user_errors.py` dokleja do wyniku ścieżkę logu — tutaj jej nie ma.
"""
from __future__ import annotations

import os

_AC_PORTS = "19723-19730"
_DEFAULT_AC_PORT = "19723"
_REPR_LIMIT = 200


def _tail(exc: BaseException) -> str:
    r = repr(exc)
    if len(r) > _REPR_LIMIT:
        r = r[:_REPR_LIMIT - 3] + "..."
    return f"\n\nTechnical details: {r}"


def describe(exc: BaseException) -> tuple[str, str]:
    """Returns (window title, body) in English for any exception."""
    msg = str(exc)
    low = msg.lower()

    if isinstance(exc, (ConnectionRefusedError, ConnectionError)) or "connection refused" in low \
            or "nie znaleziono archicad" in low or "archicad not found" in low:
        if os.environ.get("FLOORFORGE_LAUNCHED_FROM_AC") == "1":
            port = os.environ.get("FLOORFORGE_AC_PORT") or _DEFAULT_AC_PORT
            return ("Archicad",
                    "Started from Archicad, but Archicad does not answer on the JSON port. "
                    f"Check Options → Preferences → JSON API (port {port}) "
                    "and click Refresh." + _tail(exc))
        return ("Archicad",
                f"Archicad was not found on ports {_AC_PORTS}. "
                "Start Archicad with the FloorForge add-on loaded and click Refresh." + _tail(exc))
    if isinstance(exc, TimeoutError) or "timed out" in low:
        return ("Archicad",
                "Archicad does not respond (it is not responding while a dialog window is open). "
                "Close any open dialog windows in Archicad and try again." + _tail(exc))
    if (isinstance(exc, KeyError) and "librarypart" in low) or "additionalproperties" in low:
        return ("FloorForge add-on",
                "The FloorForge add-on in Archicad does not support the required parameters "
                "(e.g. libraryPart in CreateDoors). "
                "Install the bundle from the FloorForge package." + _tail(exc))
    if "infeasible" in low or "no layout" in low or low == "unknown":
        return ("No layout",
                "No layout was found for this outline and type. "
                "Try another type or enlarge the outline." + _tail(exc))
    if isinstance(exc, ValueError):
        return ("Input data", f"{msg} Correct the input and try again." + _tail(exc))
    return ("Unexpected error",
            "Something went wrong. Send the log file to the author of the application." + _tail(exc))
