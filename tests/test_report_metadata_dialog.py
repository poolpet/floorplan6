"""Stage 1 Phase 3 — ReportMetadataDialog tests (Tasks 10-14 combined)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest


# ============================================================================
# Task 10: default plot_id
# ============================================================================
def test_dialog_default_plot_id_is_set(qapp, isolated_qsettings):
    from ui.report_metadata_dialog import ReportMetadataDialog

    default_pid = f"Działka {date.today():%Y-%m-%d}"
    dlg = ReportMetadataDialog(default_plot_id=default_pid)
    assert dlg.plot_id_edit.text() == default_pid


# ============================================================================
# Task 11: accept returns metadata dict
# ============================================================================
def test_dialog_accept_returns_metadata(qapp, isolated_qsettings):
    from ui.report_metadata_dialog import ReportMetadataDialog

    dlg = ReportMetadataDialog(default_plot_id="dz. 1")
    dlg.address_edit.setText("ul. Testowa 1")
    dlg.accept()

    meta = dlg.get_metadata()
    assert meta["plot_id"] == "dz. 1"
    assert meta["plot_address"] == "ul. Testowa 1"
    assert meta["logo_path"] is None


# ============================================================================
# Task 12: cancel results in Rejected state
# ============================================================================
def test_dialog_reject_does_not_accept(qapp, isolated_qsettings):
    from PyQt5.QtWidgets import QDialog
    from ui.report_metadata_dialog import ReportMetadataDialog

    dlg = ReportMetadataDialog(default_plot_id="X")
    dlg.reject()
    assert dlg.result() == QDialog.Rejected


# ============================================================================
# Task 13: logo picker updates label + internal path
# ============================================================================
def test_logo_picker_updates_state(qapp, isolated_qsettings, tmp_path):
    from ui.report_metadata_dialog import ReportMetadataDialog

    dlg = ReportMetadataDialog(default_plot_id="X")
    # Symuluj wybor pliku z file dialog (omijamy real QFileDialog)
    fake_logo = tmp_path / "logo.png"
    fake_logo.write_bytes(b"\x89PNG\r\n\x1a\n")  # placeholder PNG bytes
    dlg._logo_path = fake_logo
    dlg.logo_path_lbl.setText("logo.png")

    assert dlg._logo_path == fake_logo
    assert "logo.png" in dlg.logo_path_lbl.text()


# ============================================================================
# Task 14: QSettings remembers last logo
# ============================================================================
def test_qsettings_persists_logo_across_instances(
    qapp, isolated_qsettings, tmp_path
):
    from ui.report_metadata_dialog import (
        QSETTINGS_APP,
        QSETTINGS_LAST_LOGO_KEY,
        QSETTINGS_ORG,
        ReportMetadataDialog,
    )
    from PyQt5.QtCore import QSettings

    # 1. Pierwsza instancja — ustaw logo + accept
    fake_logo = tmp_path / "company_logo.png"
    fake_logo.write_bytes(b"\x89PNG\r\n\x1a\n")

    dlg1 = ReportMetadataDialog(default_plot_id="X")
    dlg1._logo_path = fake_logo
    dlg1._on_accept()  # zapisuje do QSettings

    # 2. QSettings ma logo zapamiętane (jawnie IniFormat + UserScope jak w dialogu)
    s = QSettings(QSettings.IniFormat, QSettings.UserScope, QSETTINGS_ORG, QSETTINGS_APP)
    saved = s.value(QSETTINGS_LAST_LOGO_KEY, "", type=str)
    assert saved == str(fake_logo)

    # 3. Druga instancja — logo automatycznie wczytane
    dlg2 = ReportMetadataDialog(default_plot_id="Y")
    assert dlg2._logo_path == fake_logo
