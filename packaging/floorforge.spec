# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstallera dla bety FloorForge (macOS, onedir — bez .app).

Produkt = katalog dist/FloorForge/ osadzany w FloorForge.bundle/Contents/Resources/FloorForge/
(build_release.sh). Nie ma już .app ani BUNDLE(): proces odpala add-on C++
(FloorForgeLauncher) przez posix_spawn i sam ustawia FLOORFORGE_VERSION oraz
FLOORFORGE_BETA w środowisku potomka — LSEnvironment z Info.plist nie jest potrzebne.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

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
] + collect_data_files("shapely") + collect_data_files("ortools") \
  + collect_data_files("archicad", include_py_files=True)
# archicad/versioning.py robi os.scandir(archicad.releases.__path__[0]) — katalog MUSI istnieć
# na dysku w _internal/, inaczej ACConnection.connect() pada i GUI widzi "brak AC".

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
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="FloorForge", console=False)
# Produkt = katalog dist/FloorForge/ osadzany w FloorForge.bundle/Contents/Resources/FloorForge/ (build_release.sh)
coll = COLLECT(exe, a.binaries, a.datas, name="FloorForge")
