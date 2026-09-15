"""Pasek statusu połączenia z ArchiCAD: port · projekt · aktywna kondygnacja + Odśwież."""
from __future__ import annotations

import logging
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

logger = logging.getLogger(__name__)

BUSY_TEXT = "Sprawdzam…"
REFRESH_TEXT = "Odśwież"
NO_AC_TEXT = "Brak połączenia z ArchiCAD — uruchom AC z dodatkiem Tapir i kliknij Odśwież."


def launched_from_archicad() -> bool:
    """Czy aplikację odpalił add-on FloorForge (a nie user z Findera/terminala)."""
    return bool(os.environ.get("FLOORFORGE_LAUNCHED_FROM_AC")
                or os.environ.get("FLOORFORGE_AC_PORT"))


class AcStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[dict] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("ArchiCAD: nie sprawdzono")
        # Komunikat jest długi, a lewy panel wąski — bez zawijania tester widzi ucięty tekst.
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(150)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.refresh_btn = QPushButton(REFRESH_TEXT)
        self.refresh_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        # Start z add-onu: AC na pewno działa i znamy jego port — kazanie userowi klikać
        # „Odśwież" byłoby pustym krokiem. Env czytamy TU (w konstruktorze), bo timer
        # odpala się później i env mógłby się już zmienić. singleShot(0) zamiast
        # bezpośredniego refresh(): najpierw okno, potem synchroniczny skan portów.
        self._auto_refresh = launched_from_archicad()
        if self._auto_refresh:
            QTimer.singleShot(0, self.refresh)

    def refresh(self):
        """Skan portów AC (synchroniczny) — przycisk na ten czas nieaktywny."""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText(BUSY_TEXT)
        self.refresh_btn.repaint()
        try:
            self._scan()
        finally:
            self.refresh_btn.setText(REFRESH_TEXT)
            self.refresh_btn.setEnabled(True)

    def _scan(self):
        from bridge.tapir_connection import TAPIR_NAMESPACE, TapirConnection
        try:
            self.instances = TapirConnection.list_instances() or []
        except Exception as e:
            logger.warning("status AC: %r", e)
            self.instances = []
        if not self.instances:
            self.label.setText(NO_AC_TEXT)
            return
        inst = self.instances[0]
        story_txt = "?"
        try:
            # Świeże połączenie per port — tak jak list_instances. NIE wolno tu użyć
            # use_port(): TapirConnection to singleton i przestawiłoby to cel eksportu
            # wybrany przez usera w pickerze instancji.
            conn = TapirConnection._try_connect(inst["port"])
            if conn is None:
                raise ConnectionError(f"AC na porcie {inst['port']} nie odpowiada")
            cmd_id = conn.types.AddOnCommandId(TAPIR_NAMESPACE, "GetStories")
            st = conn.commands.ExecuteAddOnCommand(cmd_id, {}) or {}
            act = int(st.get("actStory", -1))
            names = {int(s.get("index", -1)): s.get("name") for s in st.get("stories", [])}
            story_txt = names.get(act) or f"idx {act}"
        except Exception as e:
            logger.warning("status AC (stories): %r", e)
        more = f" (+{len(self.instances) - 1} inne)" if len(self.instances) > 1 else ""
        self.label.setText(
            f"AC port {inst['port']} · {inst.get('projectName') or '?'} · kondygnacja {story_txt}{more}")
