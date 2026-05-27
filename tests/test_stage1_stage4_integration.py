"""Qt smoke test: Stage 1 -> Stage 4 signal/slot wiring.

Uses qapp fixture from tests/conftest.py (session-scoped QApplication;
no pytest-qt needed).
"""
from __future__ import annotations

import pytest
from shapely.geometry import LineString, box

from core.models import WallType
from core.plot_model import BoundaryType, PlotBoundary
from core.plot_subdivider import SubdivisionResult, SubPlot
from ui.main_window import MainWindow


@pytest.fixture
def mw(qapp):
    """A fresh MainWindow; relies on Stage1Widget import succeeding."""
    win = MainWindow()
    yield win
    win.close()


def _fake_subdivision_result(parent_polygon=None):
    """A minimal stand-in for SubdivisionResult — just enough for the slot path."""
    if parent_polygon is None:
        parent_polygon = box(0, 0, 12, 30)

    class _ParentStub:
        geometry = parent_polygon
        boundaries: list = []

    building = box(2, 10, 10, 20)
    sub = SubPlot(
        polygon=box(0, 0, 12, 30),
        boundaries=[
            PlotBoundary(
                geometry=LineString([(0, 0), (12, 0)]),
                boundary_type=BoundaryType.DROGA,
                segment_index=0,
                is_shared_wall=False,
            )
        ],
        proposed_building=building,
        parent_droga_touch=12.0,
        internal_road_touch=0.0,
    )
    result = SubdivisionResult(
        parent=_ParentStub(),
        sub_plots=[sub],
        roads=[],
        nieuzytek=None,
        orientation_name="smoke",
        rows=1,
        cols=1,
    )
    return result, sub


class TestSignalToSlotWiring:
    def test_slot_fills_stage4_fields_and_switches_tab(self, mw):
        assert mw.stage1_widget is not None, "Stage 1 widget must load"
        assert mw._imported_polygon is None
        result, sub = _fake_subdivision_result()
        mw.stage1_widget._mode_b_result = result
        mw.stage1_widget._selected_sub_idx = 0
        mw.stage1_widget._on_open_in_stage4()
        assert mw._imported_polygon is not None
        assert mw._imported_polygon.equals(sub.proposed_building)
        assert mw._imported_entry == pytest.approx((6.0, 10.0))
        assert mw._imported_wall_types is not None
        assert all(w in (WallType.FACADE, WallType.INTERNAL)
                   for w in mw._imported_wall_types)
        assert mw.tabs.currentWidget() is mw.apt_tab

    def test_no_signal_emit_without_proposed_building(self, mw):
        """Selection without proposed_building must not emit the signal."""
        result, sub = _fake_subdivision_result()
        sub.proposed_building = None
        mw.stage1_widget._mode_b_result = result
        mw.stage1_widget._selected_sub_idx = 0
        received = []
        mw.stage1_widget.apartment_layout_requested.connect(
            lambda *args: received.append(args)
        )
        mw.stage1_widget._on_open_in_stage4()
        assert received == []
        assert mw._imported_polygon is None
