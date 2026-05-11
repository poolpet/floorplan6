"""Tests for core.report_pdf — PDF assembly via reportlab."""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.fixtures.sample_report import make_sample_report


class TestPDFGeneration:
    def test_pdf_is_created(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        assert out.is_file()
        assert out.stat().st_size > 5000  # > 5 KB

    def test_pdf_has_cover_page(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 1
        text = reader.pages[0].extract_text()
        assert rd.plot_id in text
        assert rd.plot_address in text

    def test_pdf_has_exec_summary_and_inputs(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 3
        # Exec summary should mention WZ designed
        text2 = reader.pages[1].extract_text()
        assert "Executive summary" in text2 or "Podsumowanie" in text2
        # Data inputs should mention MPZP
        text3 = reader.pages[2].extract_text()
        assert "MPZP" in text3
