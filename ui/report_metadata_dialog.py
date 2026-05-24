"""Pre-save metadata dialog for Stage 1 PDF report export.

Collects:
    - plot_id (string, required)
    - plot_address (string, optional)
    - logo_path (Path | None, persisted via QSettings)

After construction, caller invokes exec_() and checks the return value:
    Accepted → get_metadata() returns dict
    Rejected → get_metadata() should not be called
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

QSETTINGS_ORG = "FloorPlan6"
QSETTINGS_APP = "Stage1Report"
QSETTINGS_LAST_LOGO_KEY = "last_logo_path"


class ReportMetadataDialog(QDialog):
    """Collect plot_id, plot_address, optional logo_path before PDF save."""

    def __init__(self, parent=None, default_plot_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Dane raportu")
        self.setMinimumWidth(420)

        self.plot_id_edit = QLineEdit(default_plot_id)
        self.plot_id_edit.setPlaceholderText("np. dz. 123/4, obręb 7-08-12")

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("ul. Słoneczna 12, Warszawa")

        self._logo_path: Optional[Path] = None
        self.logo_path_lbl = QLabel("(brak)")
        self.logo_btn = QPushButton("Wybierz logo…")
        self.logo_btn.clicked.connect(self._on_pick_logo)

        # Restore last-used logo
        s = QSettings(QSettings.IniFormat, QSettings.UserScope, QSETTINGS_ORG, QSETTINGS_APP)
        last = s.value(QSETTINGS_LAST_LOGO_KEY, "", type=str)
        if last and Path(last).exists():
            self._logo_path = Path(last)
            self.logo_path_lbl.setText(os.path.basename(last))

        form = QFormLayout()
        form.addRow("Identyfikator działki:", self.plot_id_edit)
        form.addRow("Adres działki:", self.address_edit)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_btn)
        logo_row.addWidget(self.logo_path_lbl, stretch=1)
        form.addRow("Logo (opcjonalne):", logo_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _on_pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz logo",
            "",
            "Obrazy (*.png *.jpg *.jpeg)",
        )
        if path:
            self._logo_path = Path(path)
            self.logo_path_lbl.setText(os.path.basename(path))

    def _on_accept(self):
        # Persist last-used logo so next run pre-fills it
        if self._logo_path is not None:
            s = QSettings(QSettings.IniFormat, QSettings.UserScope, QSETTINGS_ORG, QSETTINGS_APP)
            s.setValue(QSETTINGS_LAST_LOGO_KEY, str(self._logo_path))
        self.accept()

    def get_metadata(self) -> dict:
        """Return metadata dict. Caller MUST check exec_() == Accepted first."""
        return {
            "plot_id": self.plot_id_edit.text(),
            "plot_address": self.address_edit.text(),
            "logo_path": self._logo_path,
        }
