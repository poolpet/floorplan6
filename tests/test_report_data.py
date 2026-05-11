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


class TestEstimateUnits:
    def test_basic_pum_divided_by_avg(self):
        """Estimate floor(PUM / avg_apartment_size)."""
        from core.report_data import estimate_units
        # PUM 562 m² ÷ 55 m² = 10.2 → 10 units
        assert estimate_units(pum_m2=562.0, avg_apartment_m2=55.0) == 10

    def test_default_avg_is_55m2(self):
        from core.report_data import estimate_units
        # PUM 100 / default 55 = 1.81 → 1
        assert estimate_units(pum_m2=100.0) == 1

    def test_zero_pum_returns_zero(self):
        from core.report_data import estimate_units
        assert estimate_units(pum_m2=0.0) == 0

    def test_below_one_apartment_returns_zero(self):
        from core.report_data import estimate_units
        # PUM 40 m² < 55 m² → 0 units
        assert estimate_units(pum_m2=40.0) == 0

    def test_custom_avg_size(self):
        from core.report_data import estimate_units
        # PUM 200 ÷ 80 = 2.5 → 2
        assert estimate_units(pum_m2=200.0, avg_apartment_m2=80.0) == 2

    def test_negative_pum_raises(self):
        from core.report_data import estimate_units
        with pytest.raises(ValueError, match="non-negative"):
            estimate_units(pum_m2=-10.0)


class TestComputeHash:
    def test_hash_deterministic(self):
        from core.report_data import ReportData, compute_hash
        rd = ReportData(plot_id="dz. 1234", plot_address="x", plot_area_m2=100.0)
        h1 = compute_hash(rd)
        h2 = compute_hash(rd)
        assert h1 == h2
        assert len(h1) == 16  # short hex prefix

    def test_hash_changes_with_plot_id(self):
        from core.report_data import ReportData, compute_hash
        rd1 = ReportData(plot_id="dz. 1234", plot_address="x", plot_area_m2=100.0)
        rd2 = ReportData(plot_id="dz. 5678", plot_address="x", plot_area_m2=100.0)
        assert compute_hash(rd1) != compute_hash(rd2)

    def test_hash_ignores_generated_at(self):
        """Same input data + different timestamp = same hash."""
        from datetime import datetime
        from core.report_data import ReportData, compute_hash
        rd1 = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0,
                          generated_at=datetime(2026, 1, 1))
        rd2 = ReportData(plot_id="x", plot_address="x", plot_area_m2=100.0,
                          generated_at=datetime(2026, 12, 31))
        assert compute_hash(rd1) == compute_hash(rd2)


class TestGlossary:
    def test_glossary_has_required_terms(self):
        from core.report_data import GLOSSARY
        required = {"WZ", "WIZ", "PBC", "MPZP", "linia zabudowy", "PUM"}
        assert required.issubset(GLOSSARY.keys()), \
            f"Missing terms: {required - set(GLOSSARY.keys())}"

    def test_glossary_entries_are_non_empty(self):
        from core.report_data import GLOSSARY
        for term, definition in GLOSSARY.items():
            assert definition.strip(), f"Empty definition for term: {term}"
