"""Archicad connection status bar: port · project · active storey + Refresh."""
from __future__ import annotations

import logging
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

logger = logging.getLogger(__name__)

BUSY_TEXT = "Checking…"
REFRESH_TEXT = "Refresh"
NO_AC_TEXT = ("Not connected to Archicad — start Archicad with the FloorForge add-on "
              "and click Refresh.")
NOT_CHECKED_TEXT = "Archicad: not checked"


def launched_from_archicad() -> bool:
    """True when the FloorForge add-on started the app (not the user from Finder/terminal)."""
    return bool(os.environ.get("FLOORFORGE_LAUNCHED_FROM_AC")
                or os.environ.get("FLOORFORGE_AC_PORT"))


class AcStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[dict] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(NOT_CHECKED_TEXT)
        # The message is long and the left panel narrow — without wrapping the
        # tester sees truncated text.
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(150)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.refresh_btn = QPushButton(REFRESH_TEXT)
        self.refresh_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        # Launched from the add-on: Archicad is certainly running and we know its
        # port — telling the user to click "Refresh" would be an empty step. We read
        # the env HERE (in the constructor), because the timer fires later and the
        # env could already have changed. singleShot(0) instead of a direct
        # refresh(): window first, then the synchronous port scan.
        self._auto_refresh = launched_from_archicad()
        if self._auto_refresh:
            QTimer.singleShot(0, self.refresh)

    def refresh(self):
        """Archicad port scan (synchronous) — the button stays disabled meanwhile."""
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
            # A fresh connection per port — just like list_instances. We MUST NOT use
            # use_port() here: TapirConnection is a singleton and that would retarget
            # the export destination the user picked in the instance picker.
            conn = TapirConnection._try_connect(inst["port"])
            if conn is None:
                raise ConnectionError(
                    f"Archicad on port {inst['port']} is not responding")
            cmd_id = conn.types.AddOnCommandId(TAPIR_NAMESPACE, "GetStories")
            st = conn.commands.ExecuteAddOnCommand(cmd_id, {}) or {}
            act = int(st.get("actStory", -1))
            names = {int(s.get("index", -1)): s.get("name") for s in st.get("stories", [])}
            story_txt = names.get(act) or f"idx {act}"
        except Exception as e:
            logger.warning("status AC (stories): %r", e)
        more = f" (+{len(self.instances) - 1} more)" if len(self.instances) > 1 else ""
        self.label.setText(
            f"Archicad port {inst['port']} · {inst.get('projectName') or '?'} · "
            f"storey {story_txt}{more}")
