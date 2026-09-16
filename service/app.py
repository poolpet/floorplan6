"""Lokalny serwer HTTP mózgu FloorForge. Tylko 127.0.0.1. Stdlib — zero nowych zależności."""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bridge.plan_writer import export_plan_to_archicad
from bridge.tapir_connection import TapirConnection, connect_for_service, env_ac_port
from service.jobs import JobStore
from service.results import ResultStore
from service.solve_adapter import solve_request

logger = logging.getLogger(__name__)
VERSION = os.environ.get("FLOORFORGE_VERSION", "dev")
MAX_BODY_BYTES = 16 * 1024 * 1024  # twardy limit body — lokalny serwis, nie proxy
STOREYS = ("parter", "poddasze")
COUNTED = ("zones", "walls", "doors", "windows", "labels")


def _export_args(body: dict) -> tuple[str, int, list[str], bool]:
    """Walidacja żądania /export (angielskie komunikaty — czyta je paleta)."""
    job_id = body.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("Field 'job_id' is required.")
    variant = body.get("variant") or 0
    try:
        variant = int(variant)
    except (TypeError, ValueError):
        raise ValueError("Field 'variant' must be an integer.") from None
    storeys = body.get("storeys") or ["parter"]
    if not isinstance(storeys, list) or any(s not in STOREYS for s in storeys) or not storeys:
        raise ValueError("Field 'storeys' must be a list of 'parter' and/or 'poddasze'.")
    return job_id, variant, storeys, bool(body.get("furniture") or False)


class _Handler(BaseHTTPRequestHandler):
    store: JobStore = None        # ustawiane w start_server
    results: ResultStore = None   # ustawiane w start_server

    def log_message(self, fmt, *args):
        logger.debug("http: " + fmt, *args)

    def _json(self, code: int, body: dict):
        # default=str: wynik joba może zawierać typ spoza JSON-a; lepiej odpowiedzieć
        # niż wysypać handler w trakcie serializacji (nagłówki jeszcze nie poszły).
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _internal_error(self):
        """Ostatnia deska ratunku: klient dostaje JSON 500, nie zerwane połączenie."""
        logger.exception("http: %s %s", self.command, self.path)
        self._json(500, {"error": "Internal service error."})

    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError("The Content-Length header is invalid.") from None
        if n < 0:
            raise ValueError("The Content-Length header is invalid.")
        if n > MAX_BODY_BYTES:
            raise ValueError(f"The request body is too large (limit {MAX_BODY_BYTES // (1024 * 1024)} MB).")
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("The request body is not valid JSON.")
        if not isinstance(body, dict):
            raise ValueError("The request body must be a JSON object.")
        return body

    def do_GET(self):
        try:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/health":
                return self._json(200, {"status": "ok", "version": VERSION,
                                        "ac_port": env_ac_port(),
                                        "ac_connected": TapirConnection().connected})
            if path.startswith("/jobs/"):
                job = self.store.get(path[len("/jobs/"):])
                return self._json(200, job) if job else self._json(404, {"error": "Unknown job id."})
            self._json(404, {"error": "Unknown path."})
        except Exception:
            self._internal_error()

    def do_POST(self):
        try:
            path = urllib.parse.urlsplit(self.path).path
            try:
                body = self._read_json()
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            if path == "/solve":
                # Id joba znane PRZED startem wątku — solver pod tym kluczem
                # odkłada obiekty planów w ResultStore dla późniejszego /export.
                jid = uuid.uuid4().hex[:12]
                self.store.submit(solve_request, {**body, "_job_id": jid},
                                  store=self.results, job_id=jid)
                return self._json(202, {"job_id": jid})
            if path == "/export":
                return self._export(body)
            if path == "/shutdown":
                self._json(200, {"status": "stopping"})
                # shutdown() musi lecieć z INNEGO wątku niż serve_forever.
                threading.Thread(target=self._stop_server, name="floorforge-shutdown",
                                 daemon=True).start()
                return
            self._json(404, {"error": "Unknown path."})
        except Exception:
            self._internal_error()

    def _export(self, body: dict):
        """Wstaw zapamiętany wariant do AC. Obiekty planów — bez deserializacji kontraktu."""
        try:
            job_id, variant, storeys, furniture = _export_args(body)
        except ValueError as e:
            return self._json(400, {"error": str(e)})

        job = self.store.get(job_id)
        if job is None:
            return self._json(404, {"error": "Unknown job id."})
        status = job.get("status")
        if status == "error":
            return self._json(409, {"error": f"Generation failed: {job.get('error') or 'unknown error'}"})
        if status != "done":
            return self._json(409, {"error": "Job is not finished yet."})
        entry = self.results.get(job_id)
        if entry is None:
            return self._json(404, {"error": "Result no longer available (evicted). Generate again."})

        house = entry.get("mode") == "house"
        plans = entry.get("plans") or []
        # Zakres wariantu sprawdzamy PRZED łączeniem z AC — 404 ma być natychmiastowe.
        if not house and not 0 <= variant < len(plans):
            return self._json(404, {"error": "Unknown variant index."})
        # ConnectionError obejmuje też writera: AC może paść W TRAKCIE wstawiania.
        try:
            tapir = connect_for_service()
            if house:
                from bridge.house_export import export_house_storeys  # lazy — Task 2
                res = export_house_storeys(entry["layout"], storeys, tapir,
                                           include_furniture=furniture)
                if res.get("error"):
                    return self._json(422, {"error": res["error"], "inserted": res.get("inserted") or []})
                return self._json(200, {**(res.get("totals") or {}),
                                        "storeys": res.get("inserted") or [],
                                        "partial": bool(res.get("partial"))})
            res = export_plan_to_archicad(plans[variant], tapir=tapir, include_furniture=furniture)
        except ConnectionError as e:
            logger.warning("export: ArchiCAD nie odpowiada (%s)", e)
            return self._json(503, {"error": "Archicad does not respond on the JSON port. "
                                             "Start Archicad with the FloorForge add-on and try again."})
        except ValueError as e:
            logger.warning("export: writer odrzucił rzut (%s)", e)
            return self._json(422, {"error": str(e)})
        out = {k: len(res.get(k) or []) for k in COUNTED}
        out["storeys"] = ["parter"]   # mieszkanie = jedna kondygnacja
        return self._json(200, out)

    def _stop_server(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            logger.exception("shutdown: nie udało się zamknąć serwera")


class ServiceHandle:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self._server, self._thread = server, thread
        self._stopped = False
        self.port = server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def is_running(self) -> bool:
        return self._thread.is_alive()

    def stop(self):
        """Idempotentne — serwis mógł już zamknąć się sam po POST /shutdown."""
        if self._stopped:
            return
        self._stopped = True
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_server(host: str = "127.0.0.1", port: int = 0, job_store: JobStore | None = None,
                 result_store: ResultStore | None = None) -> ServiceHandle:
    handler = type("Handler", (_Handler,), {"store": job_store or JobStore(),
                                            "results": result_store or ResultStore()})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, name="floorforge-service", daemon=True)
    t.start()
    logger.info("service: nasłuch %s:%s (wersja %s)", host, server.server_address[1], VERSION)
    return ServiceHandle(server, t)
