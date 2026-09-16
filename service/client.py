"""Minimalny klient HTTP mózgu (urllib). Używany przez --selftest i przyszłe powłoki."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class ServiceClient:
    def __init__(self, url: str, timeout: float = 10.0):
        self.url, self.timeout = url.rstrip("/"), timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        r = urllib.request.Request(self.url + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> dict:
        return self._req("GET", "/health")

    def solve(self, req: dict) -> str:
        return self._req("POST", "/solve", req)["job_id"]

    def job(self, job_id: str) -> dict:
        return self._req("GET", f"/jobs/{job_id}")

    def export(self, req: dict) -> dict:
        """Wstaw wariant do AC. Błąd serwisu (4xx/5xx) → RuntimeError z angielskim `error`."""
        try:
            return self._req("POST", "/export", req)
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8") or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                body = {}
            finally:
                e.close()
            raise RuntimeError(body.get("error") or str(e)) from None

    def shutdown(self) -> None:
        """Poproś serwis o zamknięcie. Zerwane połączenie po odpowiedzi to nie błąd."""
        try:
            self._req("POST", "/shutdown", {})
        except (urllib.error.URLError, OSError):
            pass

    def wait(self, job_id: str, timeout: float = 120.0, poll: float = 0.2) -> dict:
        t0 = time.time()
        while True:
            j = self.job(job_id)
            if j["status"] == "done":
                return j
            if j["status"] == "error":
                raise RuntimeError(j["error"])
            if time.time() - t0 > timeout:
                raise TimeoutError(f"Job {job_id} nie skończył się w {timeout:.0f} s.")
            time.sleep(poll)
