"""
Połączenie z ArchiCAD przez Tapir Add-On (port 19723).

Singleton z retry logic. Obsługuje komendy Tapir:
- GetSelectedElements
- GetDetailsOfElements
- CreateZones
"""
from __future__ import annotations

import time
from typing import Optional

from archicad import ACConnection

ARCHICAD_PORT = 19723
CONNECT_RETRIES = 3
CONNECT_DELAY_S = 2.0
TAPIR_NAMESPACE = "TapirCommand"


class TapirConnection:
    """Singleton połączenia z ArchiCAD."""

    _instance: Optional[TapirConnection] = None
    _conn: Optional[ACConnection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def connect(self) -> bool:
        """Nawiąż połączenie z ArchiCAD. Zwraca True jeśli OK."""
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                self._conn = ACConnection.connect(port=ARCHICAD_PORT)
                return True
            except ConnectionRefusedError:
                if attempt < CONNECT_RETRIES:
                    time.sleep(CONNECT_DELAY_S)
            except Exception as e:
                if attempt < CONNECT_RETRIES:
                    time.sleep(CONNECT_DELAY_S)
                else:
                    raise ConnectionError(
                        f"Nie można połączyć z ArchiCAD (port {ARCHICAD_PORT}): {e}"
                    )
        raise ConnectionError(
            f"ArchiCAD nie odpowiada na porcie {ARCHICAD_PORT}. "
            f"Sprawdź czy ArchiCAD jest uruchomiony i czy Tapir Add-On jest zainstalowany."
        )

    @property
    def commands(self):
        if self._conn is None:
            self.connect()
        return self._conn.commands

    @property
    def types(self):
        if self._conn is None:
            self.connect()
        return self._conn.types

    def _execute_tapir(self, command_name: str, params: dict) -> dict:
        """Wykonaj komendę Tapir Add-On."""
        command_id = self.types.AddOnCommandId(TAPIR_NAMESPACE, command_name)
        result = self.commands.ExecuteAddOnCommand(command_id, params)
        return result or {}

    def get_selected_elements(self) -> list[dict]:
        """Pobierz zaznaczone elementy."""
        result = self._execute_tapir("GetSelectedElements", {})
        return result.get("elements", result.get("elementIds", []))

    def get_elements_by_type(self, element_type: str) -> list[dict]:
        """Pobierz wszystkie elementy danego typu (np. 'Door', 'Wall', 'Zone').

        Returns:
            Lista dict z elementId.guid.
        """
        result = self._execute_tapir(
            "GetElementsByType", {"elementType": element_type}
        )
        return result.get("elements", result.get("elementIds", []))

    def get_element_details(self, guids: list[str]) -> list[dict]:
        """Pobierz szczegóły elementów (współrzędne)."""
        elements = [{"elementId": {"guid": g}} for g in guids]
        result = self._execute_tapir("GetDetailsOfElements", {"elements": elements})
        return result.get("detailsOfElements", result.get("elements", []))

    def create_zones(self, zones_data: list[dict]) -> list[str]:
        """Utwórz strefy (zone) w ArchiCAD.

        Args:
            zones_data: Lista dict z kluczami: name, numberStr, polygonCoordinates

        Returns:
            Lista GUID-ów utworzonych stref.
        """
        payload = {"zonesData": zones_data}
        result = self._execute_tapir("CreateZones", payload)
        return self._extract_guids(result)

    @staticmethod
    def _extract_guids(result: dict) -> list[str]:
        """Wyodrębnij GUID-y z odpowiedzi Tapir."""
        for key in ("createdElements", "elements", "elementIds"):
            items = result.get(key, [])
            if items:
                guids = []
                for item in items:
                    eid = item.get("elementId", item) if isinstance(item, dict) else item
                    guid = eid.get("guid") if isinstance(eid, dict) else str(eid)
                    guids.append(guid)
                return guids
        return []
