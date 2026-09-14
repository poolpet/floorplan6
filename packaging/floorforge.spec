# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstallera dla bety FloorForge (macOS, onedir + .app).

Wersja wchodzi do Info.plist (LSEnvironment) — uruchomienie z Findera ma
FLOORFORGE_VERSION i FLOORFORGE_BETA. Uruchom.command ustawia je sam (z pliku
VERSION obok .app), bo LSEnvironment nie działa przy odpaleniu binarki z shella.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
VERSION = os.environ.get("FLOORFORGE_VERSION", "dev")

hiddenimports = (
    collect_submodules("ortools.sat")
    + collect_submodules("ortools.util")
    # archicad ładuje moduły wersji przez importlib (archicad/versioning.py:
    # archicad.releases.ac29.b3000commands itd.) — statyczna analiza ich nie widzi.
    + collect_submodules("archicad")
    + [
        "ortools.sat.python.cp_model",
        "shapely._geos",
        "PyQt5.sip",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_agg",
        "yaml",
    ]
)

datas = [
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "rules"), "rules"),
    (str(ROOT / "data" / "plans"), "data/plans"),
] + collect_data_files("shapely") + collect_data_files("ortools")

binaries = collect_dynamic_libs("shapely") + collect_dynamic_libs("ortools")

a = Analysis(
    [str(ROOT / "floorforge_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "reportlab", "pypdf", "jupyter", "ipywidgets", "notebook", "pytest", "tkinter",
        "core.report_pdf", "core.report_renderer", "core.report_builder",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="FloorForge", console=False,
          icon=str(ROOT / "packaging" / "icon.icns"))
coll = COLLECT(exe, a.binaries, a.datas, name="FloorForge")
app = BUNDLE(
    coll, name="FloorForge.app", icon=str(ROOT / "packaging" / "icon.icns"),
    bundle_identifier="pl.floorforge.beta",
    info_plist={
        "CFBundleName": "FloorForge",
        "CFBundleDisplayName": "FloorForge",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
        "LSEnvironment": {"FLOORFORGE_BETA": "1", "FLOORFORGE_VERSION": VERSION},
    },
)
