"""Lokalny serwer HTTP mózgu FloorForge. Tylko 127.0.0.1. Stdlib — zero nowych zależności."""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from service.jobs import JobStore
from service.solve_adapter import solve_request

logger = logging.getLogger(__name__)
VERSION = os.environ.get("FLOORFORGE_VERSION", "dev")
MAX_BODY_BYTES = 16 * 1024 * 1024  # twardy limit body — lokalny serwis, nie proxy


def export_contract(contract: dict, port: int | None = None) -> dict:
    """Eksport kontraktu do AC. Beta: GUI eksportuje w procesie (plan_writer); ten endpoint
    jest dla przyszłych powłok. Wymaga uruchomionego AC — inaczej ConnectionError."""
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    ok = tapir.use_port(port) if port else tapir.connect()
    if not ok:
        raise ConnectionError("Nie znaleziono ArchiCADa z dodatkiem Tapir.")
    raise NotImplementedError("Eksport z kontraktu JSON: po becie (GUI eksportuje z obiektów).")


class _Handler(BaseHTTPRequestHandler):
    store: JobStore = None  # ustawiane w start_server

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
        self._json(500, {"error": "Błąd wewnętrzny serwisu."})

    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError("Nagłówek Content-Length jest niepoprawny.") from None
        if n < 0:
            raise ValueError("Nagłówek Content-Length jest niepoprawny.")
        if n > MAX_BODY_BYTES:
            raise ValueError(f"Treść żądania jest za duża (limit {MAX_BODY_BYTES // (1024 * 1024)} MB).")
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Treść żądania nie jest poprawnym JSON.")
        if not isinstance(body, dict):
            raise ValueError("Treść żądania musi być obiektem JSON.")
        return body

    def do_GET(self):
        try:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/health":
                return self._json(200, {"status": "ok", "version": VERSION})
            if path.startswith("/jobs/"):
                job = self.store.get(path[len("/jobs/"):])
                return self._json(200, job) if job else self._json(404, {"error": "Nieznany job."})
            self._json(404, {"error": "Nieznana ścieżka."})
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
                jid = self.store.submit(solve_request, body)
                return self._json(202, {"job_id": jid})
            if path == "/export":
                try:
                    return self._json(200, export_contract(body.get("contract") or {}, body.get("port")))
                except ConnectionError as e:
                    return self._json(503, {"error": str(e)})
                except NotImplementedError as e:
                    return self._json(501, {"error": str(e)})
            self._json(404, {"error": "Nieznana ścieżka."})
        except Exception:
            self._internal_error()


class ServiceHandle:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self._server, self._thread = server, thread
        self.port = server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_server(host: str = "127.0.0.1", port: int = 0, job_store: JobStore | None = None) -> ServiceHandle:
    handler = type("Handler", (_Handler,), {"store": job_store or JobStore()})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, name="floorforge-service", daemon=True)
    t.start()
    logger.info("service: nasłuch %s:%s (wersja %s)", host, server.server_address[1], VERSION)
    return ServiceHandle(server, t)
