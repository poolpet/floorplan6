"""Pasek statusu połączenia z ArchiCAD: port · projekt · aktywna kondygnacja + Odśwież."""
from __future__ import annotations

import logging

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

logger = logging.getLogger(__name__)


class AcStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: list[dict] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("ArchiCAD: nie sprawdzono")
        self.refresh_btn = QPushButton("Odśwież")
        self.refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.refresh_btn)

    def refresh(self):
        from bridge.tapir_connection import TapirConnection
        try:
            self.instances = TapirConnection.list_instances() or []
        except Exception as e:
            logger.warning("status AC: %r", e)
            self.instances = []
        if not self.instances:
            self.label.setText("Brak połączenia z ArchiCAD — uruchom AC z dodatkiem Tapir i kliknij Odśwież.")
            return
        inst = self.instances[0]
        story_txt = "?"
        try:
            t = TapirConnection()
            t.use_port(inst["port"])
            st = t.get_stories() or {}
            act = int(st.get("actStory", -1))
            names = {int(s.get("index", -1)): s.get("name") for s in st.get("stories", [])}
            story_txt = names.get(act) or f"idx {act}"
        except Exception as e:
            logger.warning("status AC (stories): %r", e)
        more = f" (+{len(self.instances) - 1} inne)" if len(self.instances) > 1 else ""
        self.label.setText(
            f"AC port {inst['port']} · {inst.get('projectName') or '?'} · kondygnacja {story_txt}{more}")
