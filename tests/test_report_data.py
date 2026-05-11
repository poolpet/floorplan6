"""Tests for core.report_data — ReportData dataclass and helpers."""
from __future__ import annotations

import pytest

from core.report_data import ReportData


class TestReportDataConstruction:
    def test_minimal_construction(self):
        """ReportData can be created with minimal required fields."""
        rd = ReportData(
            plot_id="dz. 1234/5",
            plot_address="ul. Przykładowa 12, Warszawa",
            plot_area_m2=1247.0,
        )
        assert rd.plot_id == "dz. 1234/5"
        assert rd.plot_area_m2 == 1247.0
        # Optional collections default to empty
        assert rd.verification_results == []
        assert rd.buildup_variants == []

    def test_all_fields_present(self):
        """All required ReportData attribute names exist."""
        rd = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0)
        for attr in [
            "plot_id", "plot_address", "plot_area_m2", "plot_perimeter_m",
            "mpzp_summary", "buildable_zone_m2", "buildable_zone_percent",
            "setbacks", "indicators", "verification_results", "buildup_variants",
            "logo_path", "generated_at", "tool_version", "pack_version",
            "data_hash",
        ]:
            assert hasattr(rd, attr), f"Missing attribute: {attr}"
