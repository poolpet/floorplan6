"""Log techniczny na dysku: ~/Library/Logs/FloorForge/floorforge.log, rotacja 5 × 2 MB.

Tylko stdlib (`logging`), bez sieci. Katalog można nadpisać zmienną środowiskową
`FLOORFORGE_LOG_DIR` (używają jej testy, żeby nie pisać do katalogu użytkownika).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

LOG_FILENAME = "floorforge.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 5

_LOG_PATH: Path | None = None


def _log_dir(app_name: str) -> Path:
    env = os.environ.get("FLOORFORGE_LOG_DIR")
    if env:
        return Path(env)
    return Path.home() / "Library" / "Logs" / app_name


def _our_handlers() -> list[logging.handlers.RotatingFileHandler]:
    """Handlery FloorForge już wpięte w root — także te z poprzedniej instancji
    modułu (testy robią importlib.reload, co zeruje `_LOG_PATH`)."""
    out = []
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler) and \
                os.path.basename(getattr(h, "baseFilename", "")) == LOG_FILENAME:
            out.append(h)
    return out


def setup_logging(app_name: str = "FloorForge") -> Path:
    """Wpina rotujący handler plikowy w root logger. Idempotentne — nigdy nie
    dokłada drugiego handlera dla tego samego pliku. Zwraca ścieżkę logu."""
    global _LOG_PATH
    path = _log_dir(app_name) / LOG_FILENAME
    target = os.path.abspath(str(path))

    root = logging.getLogger()
    existing = _our_handlers()
    if _LOG_PATH is not None and os.path.abspath(str(_LOG_PATH)) == target and existing:
        return _LOG_PATH
    for h in existing:
        if h.baseFilename == target:
            # Ten sam plik — nic nie dokładamy (np. po reloadzie modułu).
            _LOG_PATH = path
            _set_level(root)
            return path
        # Inny katalog (zmienione FLOORFORGE_LOG_DIR) — zdejmij stary handler,
        # inaczej po reloadzie modułu handlery by się kumulowały.
        root.removeHandler(h)
        h.close()

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    _set_level(root)
    _LOG_PATH = path
    return path


def _set_level(root: logging.Logger) -> None:
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def log_path() -> Path | None:
    """Ścieżka pliku logu albo None, gdy `setup_logging()` nie było wołane."""
    return _LOG_PATH
