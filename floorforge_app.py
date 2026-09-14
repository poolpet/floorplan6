"""Entry point zamrożonej aplikacji FloorForge (beta). Patrz packaging/floorforge.spec."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SELFTEST_REQ = {"mode": "apartment", "polygon": [[0, 0], [8, 0], [8, 6], [0, 6]],
                "entry": [4, 0], "mtype": "M2", "max_variants": 1}


def _version() -> str:
    return os.environ.get("FLOORFORGE_VERSION", "dev")


def selftest() -> int:
    from service.app import start_server
    from service.client import ServiceClient
    h = start_server(port=0)
    try:
        c = ServiceClient(h.url)
        c.health()
        job = c.wait(c.solve(SELFTEST_REQ), timeout=120)
        variants = job["result"].get("variants", [])
        if not variants:
            print("SELFTEST FAIL: solver nie zwrócił wariantów")
            return 1
        n_rooms = len(variants[0].get("rooms", []))
        print(f"SELFTEST OK: {len(variants)} wariantów, {n_rooms} pokoi, wersja {_version()}")
        return 0
    except Exception as e:
        print(f"SELFTEST FAIL: {e!r}")
        return 1
    finally:
        h.stop()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    os.environ.setdefault("FLOORFORGE_BETA", "1")
    from ui.app_logging import setup_logging
    setup_logging()
    if "--version" in argv:
        print(_version())
        return 0
    if "--selftest" in argv:
        return selftest()
    from ui.main_window import run_gui
    run_gui()   # sys.exit wewnątrz
    return 0


if __name__ == "__main__":
    sys.exit(main())
