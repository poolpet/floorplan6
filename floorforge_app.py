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
    # Wszystko w try: w paczce najczęściej wysypie się sam import serwisu
    # (brakujący hidden import) — tester ma zobaczyć SELFTEST FAIL, nie traceback.
    h = None
    try:
        from service.app import start_server
        from service.client import ServiceClient
        h = start_server(port=0)
        c = ServiceClient(h.url)
        c.health()
        job = c.wait(c.solve(SELFTEST_REQ), timeout=120)
        variants = job["result"].get("variants", [])
        if not variants:
            print("SELFTEST FAIL: the solver returned no variants")
            return 1
        # Po zmianie kontraktu /solve pokoje siedzą w variants[i]["contract"];
        # fallback na sam wariant zostaje dla starych mocków w testach.
        v0 = variants[0]
        n_rooms = len(v0.get("contract", v0).get("rooms", []))
        print(f"SELFTEST OK: {len(variants)} variants, {n_rooms} rooms, version {_version()}")
        return 0
    except Exception as e:
        print(f"SELFTEST FAIL: {e!r}")
        return 1
    finally:
        if h is not None:
            h.stop()


def ac_probe() -> int:
    """Diagnostics: connect to Archicad (FLOORFORGE_AC_PORT or scan) and print product/project info."""
    try:
        from bridge.tapir_connection import TapirConnection, env_ac_port
        t = TapirConnection()
        t.connect()
        port = t.active_port
        ver = t.commands.GetProductInfo()
        info = {}
        try:
            cid = t.types.AddOnCommandId("FloorForgeCommand", "GetProjectInfo")
            info = t.commands.ExecuteAddOnCommand(cid, {}) or {}
        except Exception as e:  # add-on command missing → still a useful signal
            info = {"addon_error": repr(e)}
        print(f"AC-PROBE OK: port={port} env_port={env_ac_port()} product={ver} project={info}")
        return 0
    except Exception as e:
        print(f"AC-PROBE FAIL: {e!r}")
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--version" in argv:
        # Czysty odczyt: bez trybu beta, bez pliku logu, bez importu Qt/serwisu.
        print(_version())
        return 0
    os.environ.setdefault("FLOORFORGE_BETA", "1")
    from ui.app_logging import setup_logging
    setup_logging()
    if "--ac-probe" in argv:
        return ac_probe()
    if "--selftest" in argv:
        return selftest()
    from ui.main_window import run_gui
    run_gui()   # sys.exit wewnątrz
    return 0


if __name__ == "__main__":
    sys.exit(main())
