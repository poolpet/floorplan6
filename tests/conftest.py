"""Shared test fixtures for FloorPlan6.

- _isolated_env: autouse — FLOORFORGE_LOG_DIR -> tmp_path (log aplikacji nigdy
  nie trafia do prawdziwego ~/Library/Logs) + kasuje FLOORFORGE_BETA, żeby tryb
  beta nie wyciekał między testami.
- qapp: session-scoped QApplication for PyQt5 dialog tests.
- isolated_qsettings: redirects QSettings file storage to tmp_path so tests
  do not pollute the user's real ~/.config/FloorPlan6/Stage1Report.conf.
- make_minimal_plot: constructs a fully-populated Plot with buildable zone,
  used by Stage 1 Phase 3 report tests.
"""
from __future__ import annotations

import sys

import pytest
from shapely.geometry import LineString, Polygon

from core.buildable_zone import BuildableZoneBuilder
from core.plot_model import (
    BoundaryType,
    HousingType,
    MPZPParameters,
    Plot,
    PlotBoundary,
)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Izoluj środowisko procesu testowego przed każdym testem.

    1. FLOORFORGE_LOG_DIR -> tmp_path: nigdy nie pisz logu aplikacji do
       prawdziwego ~/Library/Logs podczas testów.
    2. Skasuj FLOORFORGE_BETA: `floorforge_app.main()` robi
       `os.environ.setdefault("FLOORFORGE_BETA", "1")` na PRAWDZIWYM środowisku,
       więc bez tego każdy test po `tests/test_selftest.py` leciałby w trybie
       beta (polskie etykiety, jedna zakładka) i sypał się w pełnym przebiegu.
    3. Skasuj FLOORFORGE_AC_PORT i FLOORFORGE_LAUNCHED_FROM_AC: gdy aplikację
       uruchamia add-on ArchiCADa, obie zmienne siedzą w prawdziwym środowisku
       i zmieniłyby wynik `TapirConnection.connect()` oraz treść komunikatów
       z `ui.user_errors.describe()`.
    """
    monkeypatch.setenv("FLOORFORGE_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    monkeypatch.delenv("FLOORFORGE_AC_PORT", raising=False)
    monkeypatch.delenv("FLOORFORGE_LAUNCHED_FROM_AC", raising=False)


@pytest.fixture(scope="session")
def qapp():
    """Provide a session-scoped QApplication for PyQt5 dialog tests."""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PyQt5 not available")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else [""])
    yield app


@pytest.fixture
def isolated_qsettings(tmp_path):
    """Redirect QSettings IniFormat UserScope to tmp_path so tests are isolated.

    Plus clear FloorPlan6/Stage1Report ini przed każdym testem — bo QSettings
    cache'uje wartości w pamięci, więc samego setPath nie wystarcza.
    """
    try:
        from PyQt5.QtCore import QSettings
    except ImportError:
        pytest.skip("PyQt5 not available")

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path),
    )
    # Reset cached state for FP6 dialog QSettings
    s = QSettings("FloorPlan6", "Stage1Report")
    s.clear()
    s.sync()
    yield tmp_path
    # Cleanup po teście — kolejny test dostanie pusty stan
    s = QSettings("FloorPlan6", "Stage1Report")
    s.clear()
    s.sync()


def make_minimal_plot(
    width: float = 40.0,
    depth: float = 30.0,
    housing_type: HousingType = HousingType.JEDNORODZINNA,
    infrastructure_municipal: bool = True,
) -> Plot:
    """Build a rectangular plot with 4 boundaries and computed buildable zone."""
    poly = Polygon([(0, 0), (width, 0), (width, depth), (0, depth)])
    coords = [(0, 0), (width, 0), (width, depth), (0, depth), (0, 0)]
    types = [
        BoundaryType.DROGA,
        BoundaryType.SASIAD_ZABUDOWANY,
        BoundaryType.WLASNA,
        BoundaryType.SASIAD_NIEZABUDOWANY,
    ]
    boundaries = [
        PlotBoundary(LineString([coords[i], coords[i + 1]]), types[i], i)
        for i in range(4)
    ]
    plot = Plot(
        number="P-test",
        geometry=poly,
        boundaries=boundaries,
        mpzp=MPZPParameters(
            max_wz=0.30,
            max_wiz=0.60,
            min_pbc_percent=40.0,
            max_height=9.0,
            setback_from_road=5.0,
            max_floors=2,
            przeznaczenie="MN",
            parking_spaces_per_unit=2.0,
            infrastructure_municipal=infrastructure_municipal,
        ),
        housing_type=housing_type,
    )
    BuildableZoneBuilder().compute(plot)
    return plot
