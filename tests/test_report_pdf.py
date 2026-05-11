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

    def test_pdf_has_buildable_and_indicators_pages(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 5

    def test_pdf_has_compliance_and_variants_pages(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 7
        compliance_text = reader.pages[5].extract_text()
        assert "wt_001" in compliance_text or "Odległość" in compliance_text

    def test_pdf_has_glossary_and_metadata(self, tmp_path):
        from core.report_pdf import generate_pdf
        rd = make_sample_report()
        out = tmp_path / "report.pdf"
        generate_pdf(rd, out)
        reader = PdfReader(out)
        assert len(reader.pages) >= 9
        # Locate by content (page index may shift as variants/etc. grow).
        all_text = [p.extract_text() for p in reader.pages]
        glossary = next(
            (t for t in all_text if "Słowniczek" in t and "MPZP" in t and "WZ" in t),
            None,
        )
        assert glossary is not None, "Glossary page not found"
        metadata = next((t for t in all_text if rd.data_hash in t), None)
        assert metadata is not None, "Metadata page (with hash) not found"
        assert "disclaimer" in metadata.lower() or "informacyjny" in metadata.lower()

    def test_pdf_with_logo(self, tmp_path):
        from core.report_pdf import generate_pdf
        from tests.fixtures.sample_report import make_sample_logo
        logo_path = make_sample_logo(tmp_path / "logo.png")
        rd = make_sample_report()
        rd.logo_path = logo_path
        out = tmp_path / "report_with_logo.pdf"
        generate_pdf(rd, out)
        assert out.is_file()
        # PDF with logo should be larger than without (image bytes embedded)
        assert out.stat().st_size > 25000


class TestCLI:
    def test_cli_generates_sample(self, tmp_path, monkeypatch):
        """Running `python -m core.report_pdf --fixture sample --out X` works."""
        import subprocess
        out = tmp_path / "cli_sample.pdf"
        result = subprocess.run(
            ["python3", "-m", "core.report_pdf", "--fixture", "sample", "--out", str(out)],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.is_file()
        assert out.stat().st_size > 20000  # at least 20 KB for 9 pages
