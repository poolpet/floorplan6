"""Proste joby w wątkach: status, postęp, wynik. Bez kolejki — beta = 1 użytkownik."""
from __future__ import annotations

import copy
import logging
import threading
import uuid

logger = logging.getLogger(__name__)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, fn, *args, job_id: str | None = None, **kwargs) -> str:
        """`job_id` z zewnątrz: handler zna id przed startem wątku (wkłada je w żądanie)."""
        jid = job_id or uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[jid] = {"id": jid, "status": "queued",
                               "progress": {"current": 0, "total": 0},
                               "result": None, "error": None}

        def progress(current, total):
            with self._lock:
                self._jobs[jid]["progress"] = {"current": int(current), "total": int(total)}

        def run():
            with self._lock:
                self._jobs[jid]["status"] = "running"
            try:
                result = fn(*args, progress=progress, **kwargs)
                with self._lock:
                    self._jobs[jid].update(status="done", result=result)
            except Exception as e:
                logger.exception("job %s: błąd", jid)
                with self._lock:
                    self._jobs[jid].update(status="error", error=str(e))

        threading.Thread(target=run, name=f"job-{jid}", daemon=True).start()
        return jid

    def get(self, jid: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(jid)
            return copy.deepcopy(j) if j else None
