"""Wyniki jobów w pamięci (obiekty planów) — /export wstawia bez deserializacji kontraktu."""
from __future__ import annotations

import threading
from collections import OrderedDict


class ResultStore:
    """LRU na `job_id -> {"mode", "boundary", "plans" | "layout"}`. Wątkobezpieczny."""

    LIMIT = 20

    def __init__(self, limit: int | None = None):
        self._limit = limit or self.LIMIT
        self._d: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()

    def put(self, job_id: str, entry: dict) -> None:
        with self._lock:
            self._d[job_id] = entry
            self._d.move_to_end(job_id)
            while len(self._d) > self._limit:
                self._d.popitem(last=False)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            e = self._d.get(job_id)
            if e is not None:
                self._d.move_to_end(job_id)
            return e
