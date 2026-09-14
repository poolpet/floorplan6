"""Log techniczny na dysku: rotacja, idempotencja setup_logging()."""
import logging


def test_setup_logging_creates_rotating_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORFORGE_LOG_DIR", str(tmp_path))
    import importlib
    import ui.app_logging as al
    importlib.reload(al)
    p = al.setup_logging()
    logging.getLogger("floorforge.test").info("hello")
    for h in logging.getLogger().handlers:
        h.flush()
    assert p == tmp_path / "floorforge.log"
    assert "hello" in p.read_text(encoding="utf-8")
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1 and handlers[0].maxBytes == 2 * 1024 * 1024 and handlers[0].backupCount == 5
    assert al.setup_logging() == p           # idempotentne — nie dubluje handlerów
    assert len([h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]) == 1
