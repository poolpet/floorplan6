"""Exception -> (title, body) in English dla GUI: mapa z `service.errors` + ścieżka logu.

Mapowanie żyje w `service/errors.py` (bez Qt, używa go także serwis HTTP);
tutaj dokładamy tylko linię `Log:` — GUI ma plik logu, serwis odpowiada JSON-em.
"""
from __future__ import annotations

from service.errors import describe as _describe_core
from ui.app_logging import log_path

_TECH_MARKER = "\n\nTechnical details:"


def describe(exc: BaseException) -> tuple[str, str]:
    """Returns (window title, body) in English for any exception."""
    title, text = _describe_core(exc)
    lp = log_path()
    if not lp:
        return title, text
    # `Log:` PRZED sekcją techniczną — ogon po "Technical details:" to sam repr
    # wyjątku (ucinany do limitu), bez doklejonej ścieżki.
    head, marker, tail = text.partition(_TECH_MARKER)
    return title, f"{head}\n\nLog: {lp}{marker}{tail}"
