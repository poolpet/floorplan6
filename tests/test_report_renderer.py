"""Smoke tests for core.report_renderer matplotlib figures."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.sample_report import make_sample_report


class TestPlotZoneFigure:
    def test_returns_figure(self):
        from core.report_renderer import plot_zone_figure
        from matplotlib.figure import Figure
        rd = make_sample_report()
        fig = plot_zone_figure(rd)
        assert isinstance(fig, Figure)

    def test_savefig_produces_png(self, tmp_path):
        from core.report_renderer import plot_zone_figure
        rd = make_sample_report()
        fig = plot_zone_figure(rd)
        out = tmp_path / "plot_zone.png"
        fig.savefig(out, dpi=100)
        assert out.is_file()
        assert out.stat().st_size > 1024  # > 1 KB


class TestIndicatorsBarChart:
    def test_returns_figure(self):
        from core.report_renderer import indicators_bar_chart
        from matplotlib.figure import Figure
        rd = make_sample_report()
        fig = indicators_bar_chart(rd)
        assert isinstance(fig, Figure)

    def test_renders_with_empty_indicators(self):
        """Should not crash if indicators list is empty."""
        from core.report_data import ReportData
        from core.report_renderer import indicators_bar_chart
        rd = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0)
        fig = indicators_bar_chart(rd)
        assert fig is not None  # graceful handling
