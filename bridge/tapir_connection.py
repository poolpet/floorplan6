"""
Połączenie z ArchiCAD przez Tapir Add-On.

Wspiera **wiele uruchomionych instancji AC** — port scanning od 19723 w górę.
Gdy aktywnych jest kilka instancji, preferowana jest ta która ma aktualnie
**aktywne zaznaczenie** (czyli ta z którą pracuje user). Bez zaznaczenia
łączy się z pierwszą odpowiadającą.

Komendy Tapir:
- GetSelectedElements
- GetDetailsOfElements
- CreateZones
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from archicad import ACConnection

ARCHICAD_PORT_START = 19723
ARCHICAD_PORT_RANGE = 8                # scan 19723..19730
CONNECT_RETRIES = 3
CONNECT_DELAY_S = 2.0
TAPIR_NAMESPACE = "TapirCommand"


class TapirConnection:
    """Singleton połączenia z ArchiCAD z auto port-scanning."""

    _instance: Optional[TapirConnection] = None
    _conn: Optional[ACConnection] = None
    _active_port: Optional[int] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def _try_connect(port: int) -> Optional[ACConnection]:
        """Try one port, return ACConnection or None."""
        try:
            return ACConnection.connect(port=port)
        except Exception:
            return None

    @staticmethod
    def _has_selection(conn: ACConnection) -> bool:
        """Check whether this AC instance has an active selection."""
        try:
            cmd_id = conn.types.AddOnCommandId(TAPIR_NAMESPACE, "GetSelectedElements")
            result = conn.commands.ExecuteAddOnCommand(cmd_id, {}) or {}
            elements = result.get("elements") or result.get("elementIds") or []
            return bool(elements)
        except Exception:
            return False

    def _scan_for_archicad(self) -> Tuple[int, ACConnection]:
        """Scan ports 19723..19730. Prefer instance with active selection.

        Returns (port, ACConnection). Raises ConnectionError if none found.
        """
        candidates: List[Tuple[int, ACConnection, bool]] = []
        ports = range(ARCHICAD_PORT_START,
                      ARCHICAD_PORT_START + ARCHICAD_PORT_RANGE)
        for port in ports:
            conn = self._try_connect(port)
            if conn is None:
                continue
            has_sel = self._has_selection(conn)
            candidates.append((port, conn, has_sel))

        if not candidates:
            raise ConnectionError(
                f"Żadna instancja ArchiCAD nie odpowiada na portach "
                f"{ARCHICAD_PORT_START}..{ARCHICAD_PORT_START + ARCHICAD_PORT_RANGE - 1}. "
                f"Sprawdź czy AC jest uruchomiony i Tapir Add-On zainstalowany."
            )

        # Prefer the AC instance that currently has a selection (= user is
        # actively working there). Else return the first that responded.
        with_sel = [c for c in candidates if c[2]]
        if with_sel:
            port, conn, _ = with_sel[0]
        else:
            port, conn, _ = candidates[0]
        return port, conn

    def connect(self) -> bool:
        """Nawiąż połączenie z którąkolwiek dostępną instancją AC.

        Strategia:
          1. Jeśli mamy zapisany ostatni działający port — spróbuj tam.
          2. W przeciwnym razie skanuj 19723..19730 i wybierz tę z zaznaczeniem.
        """
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                # Re-check known port first if we had one.
                if self._active_port is not None:
                    conn = self._try_connect(self._active_port)
                    if conn is not None:
                        # If the cached AC has selection, use it; otherwise
                        # rescan to find a better candidate.
                        if self._has_selection(conn):
                            self._conn = conn
                            return True
                        # No selection on cached port — try fresh scan.
                port, conn = self._scan_for_archicad()
                self._active_port = port
                self._conn = conn
                return True
            except ConnectionError:
                if attempt < CONNECT_RETRIES:
                    time.sleep(CONNECT_DELAY_S)
                else:
                    raise

        raise ConnectionError(
            "ArchiCAD nie odpowiada na żadnym ze skanowanych portów."
        )

    @classmethod
    def list_instances(cls, port_range=None) -> list[dict]:
        """Wykryte instancje AC: [{port, projectName, projectPath}] (deterministyczny picker).

        Świeże połączenie per port (NIE mutuje singletona), nazwa via Tapir GetProjectInfo.
        Martwy port pominięty; brak nazwy → "(nieznany)".
        """
        if port_range is None:
            port_range = range(ARCHICAD_PORT_START,
                               ARCHICAD_PORT_START + ARCHICAD_PORT_RANGE)
        out: List[dict] = []
        for port in port_range:
            conn = cls._try_connect(port)
            if conn is None:
                continue
            name, path = "(nieznany)", ""
            try:
                cid = conn.types.AddOnCommandId(TAPIR_NAMESPACE, "GetProjectInfo")
                info = conn.commands.ExecuteAddOnCommand(cid, {}) or {}
                name = info.get("projectName") or "(nieznany)"
                path = info.get("projectPath", "") or ""
            except Exception:
                pass
            out.append({"port": port, "projectName": name, "projectPath": path})
        return out

    def use_port(self, port: int) -> bool:
        """Połącz z JAWNYM portem (bez scan/prefer-selection). Determinizm celu eksportu."""
        conn = self._try_connect(port)
        if conn is None:
            raise ConnectionError(
                f"ArchiCAD na porcie {port} nie odpowiada (Tapir Add-On?)."
            )
        self._active_port = port
        self._conn = conn
        return True

    def get_stories(self) -> dict:
        """Struktura kondygnacji: {actStory, firstStory, lastStory, stories:[...]} (Tapir GetStories)."""
        return self._execute_tapir("GetStories", {})

    def get_project_info(self) -> dict:
        """Info projektu: {projectName, projectPath, ...} (Tapir GetProjectInfo)."""
        return self._execute_tapir("GetProjectInfo", {})

    @property
    def active_port(self) -> Optional[int]:
        """Port currently being used (informational)."""
        return self._active_port

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

    def get_all_walls(self) -> list[dict]:
        """Pobierz wszystkie ściany z projektu z begC/endC w details.

        Returns:
            Lista dict z kluczami: guid, beg=(x,y), end=(x,y), height, thickness
        """
        elements = self.get_elements_by_type("Wall")
        if not elements:
            print("[get_all_walls] 0 ścian na aktywnej kondygnacji/oknie "
                  "(GetElementsByType = scope aktywnej bazy planu) — okna pominięte. "
                  "Sprawdź, czy aktywne okno AC to plan właściwej kondygnacji.")
            return []
        guids = []
        for e in elements:
            if isinstance(e, dict):
                eid = e.get("elementId", e)
                guid = eid.get("guid") if isinstance(eid, dict) else str(eid)
                if guid:
                    guids.append(guid)
        details = self.get_element_details(guids)
        out = []
        for guid, d in zip(guids, details):
            if not isinstance(d, dict):
                continue
            inner = d.get("details", d)
            beg = inner.get("begCoordinate") or d.get("begCoordinate")
            end = inner.get("endCoordinate") or d.get("endCoordinate")
            if not beg or not end:
                continue
            out.append({
                "guid": guid,
                "beg": (float(beg["x"]), float(beg["y"])),
                "end": (float(end["x"]), float(end["y"])),
                "height": float(inner.get("height", 2.7)),
                "thickness": float(inner.get("thickness", 0.10)),
            })
        return out

    def create_temp_zone_at_point(
        self, x: float, y: float, name: str = "_temp_fp6_",
        category_guid: str | None = None,
    ) -> str | None:
        """Utwórz Zone w punkcie (x, y) z auto-detect obrysu (manual=false).

        Tapir 1.4.0 mapuje geometry.referencePosition → element.zone.manual=false
        → ArchiCAD automatycznie wykrywa zamknięty obrys ścian wokół punktu.
        Patrz: ElementCreationCommands.cpp CreateZonesCommand::SetTypeSpecificParameters.

        Args:
            x, y: Punkt referencyjny w metrach (world coords ArchiCAD).
            name: Nazwa tymczasowej zony.
            category_guid: Opcjonalny GUID kategorii zony.

        Returns:
            GUID utworzonej Zone, lub None gdy AC nie znalazł zamkniętego obrysu.
        """
        zone_data: dict = {
            "name": name,
            "numberStr": "TMP",
            "geometry": {"referencePosition": {"x": x, "y": y}},
            "stampPosition": {"x": x, "y": y},
        }
        if category_guid:
            zone_data["categoryAttributeId"] = {"guid": category_guid}

        result = self._execute_tapir("CreateZones", {"zonesData": [zone_data]})
        guids = self._extract_guids(result)
        return guids[0] if guids else None

    def get_zone_polygon(self, zone_guid: str) -> list[tuple[float, float]]:
        """Odczytaj polygonOutline danej Zone."""
        details = self.get_element_details([zone_guid])
        if not details or not isinstance(details[0], dict):
            return []
        inner = details[0].get("details", details[0])
        outline = inner.get("polygonOutline") or inner.get("polygon") or []
        pts = []
        for p in outline:
            if isinstance(p, dict) and "x" in p and "y" in p:
                pts.append((float(p["x"]), float(p["y"])))
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return pts

    def delete_elements(self, guids: list[str]) -> int:
        """Usuń elementy z projektu. Zwraca liczbę usuniętych."""
        if not guids:
            return 0
        elements = [{"elementId": {"guid": g}} for g in guids]
        result = self._execute_tapir("DeleteElements", {"elements": elements})
        # Tapir zwraca executionResults — jeśli success=True, element usuniety.
        if isinstance(result, dict):
            results = result.get("executionResults", [])
            return sum(1 for r in results
                       if isinstance(r, dict) and r.get("success"))
        return 0

    def create_openings(self, openings_data: list[dict]) -> list[str]:
        """Utwórz otwory bez skrzydła (Tapir 1.4.0 CreateOpenings).

        Args:
            openings_data: Lista dict z polami:
                ownerElementId: {guid} — GUID ściany
                basePoint: {x, y, z} — dolny lewy róg otworu (globalne 3D)
              Opcjonalne:
                width, height: float > 0
        """
        if not openings_data:
            return []
        payload = {"openingsData": openings_data}
        result = self._execute_tapir("CreateOpenings", payload)
        return self._extract_guids(result)

    def create_windows(self, windows_data: list[dict]) -> list[str]:
        """Utwórz okna w ArchiCAD (Tapir 1.4.0 CreateWindows).

        Args:
            windows_data: Lista dict z polami:
                ownerWallId: {guid} (wymagane)
                centerOffset: float ≥ 0 (wymagane)
                width, height, sillHeight: float (opcjonalne)
        """
        if not windows_data:
            return []
        payload = {"windowsData": windows_data}
        result = self._execute_tapir("CreateWindows", payload)
        return self._extract_guids(result)

    def create_labels(self, labels_data: list[dict]) -> list[str]:
        """Utwórz etykiety w ArchiCAD (Tapir 1.4.0 CreateLabels).

        Args:
            labels_data: Lista dict z polami:
                text: string (treść etykiety)
                begCoordinate: {x, y} (początek linii odniesienia)
                parentElementId: {guid} (opcjonalne — associative label)
                floorInd: int (opcjonalne)
            Wymagane: jeden z parentElementId / begCoordinate.
        """
        if not labels_data:
            return []
        payload = {"labelsData": labels_data}
        result = self._execute_tapir("CreateLabels", payload)
        return self._extract_guids(result)

    def create_doors(self, doors_data: list[dict]) -> list[str]:
        """Utwórz drzwi w ArchiCAD (Tapir 1.4.0 CreateDoors).

        Args:
            doors_data: Lista dict z wymaganymi kluczami (per schema 1.4.0):
                ownerWallId: {guid}  — GUID ściany na której wstawiamy drzwi
                centerOffset: float ≥ 0 — odległość od begC ściany wzdłuż niej
              Opcjonalne:
                width, height: float > 0
                sillHeight: float

        Returns:
            Lista GUID-ów utworzonych drzwi.
        """
        if not doors_data:
            return []
        payload = {"doorsData": doors_data}
        result = self._execute_tapir("CreateDoors", payload)
        return self._extract_guids(result)

    def create_walls(self, walls_data: list[dict]) -> list[str]:
        """Utwórz ściany w ArchiCAD (Tapir 1.4.0 CreateWalls).

        Args:
            walls_data: Lista dict z wymaganymi kluczami (per schema 1.4.0):
                begCoordinate: {x, y}
                endCoordinate: {x, y}
                zCoordinate: float (poziom Z dolnej krawędzi)
                height: float > 0 (wysokość ściany)
                thickness: float > 0 (grubość ściany)
              Opcjonalne:
                offset: float (przesunięcie od linii referencyjnej)
                structureType: "Basic" | "Composite" | "Profile"
                buildingMaterialId / compositeId / profileId

        Returns:
            Lista GUID-ów utworzonych ścian.
        """
        if not walls_data:
            return []
        payload = {"wallsData": walls_data}
        result = self._execute_tapir("CreateWalls", payload)
        return self._extract_guids(result)

    def create_objects(self, objects_data: list[dict]) -> list[str]:
        """Utwórz obiekty biblioteczne (meble) w ArchiCAD (Tapir CreateObjects).

        Args:
            objects_data: Lista dict z polami (schemat additionalProperties:false):
                libraryPartName: str — dokładna nazwa obiektu z biblioteki AC
                coordinates: {x, y, z} — kotwica (lewy-dolny róg obrysu obiektu)
                dimensions: {x, y} — wymiary (orientacja przez x/y; kąt NIEobsługiwany)

        Returns:
            Lista GUID-ów utworzonych obiektów (pomija te z błędem per-obiekt,
            np. "Not found library part with name X").
        """
        if not objects_data:
            return []
        result = self._execute_tapir("CreateObjects", {"objectsData": objects_data})
        return [g for g in self._extract_guids(result) if g]

    def get_gdl_parameters(self, guids: list[str]) -> list[dict]:
        """Pobierz parametry GDL elementów (Tapir GetGDLParametersOfElements).

        Returns: lista (po jednej na element) list paramów {name, type, value, ...}.
        """
        if not guids:
            return []
        elements = [{"elementId": {"guid": g}} for g in guids]
        result = self._execute_tapir("GetGDLParametersOfElements", {"elements": elements})
        return result.get("gdlParametersOfElements", [])

    def set_gdl_parameters(self, elements_with_params: list[dict]) -> dict:
        """Ustaw parametry GDL elementów (Tapir SetGDLParametersOfElements).

        Args:
            elements_with_params: lista dict gotowych pod schemat:
                {"elementId": {"guid": G},
                 "gdlParameters": [{"name": "A", "value": 1.6}, ...]}
              (np. z core.furniture_extractor.furniture_to_gdl_payload). Dla obiektów
              ustawia A/B (Length, w metrach) → realny rozmiar 2D/3D; to JEDYNA komenda
              Tapira realnie zapisująca A/B (CreateObjects.dimensions = tylko xRatio/yRatio).

        Returns:
            Surowy wynik (zawiera executionResults).
        """
        if not elements_with_params:
            return {}
        return self._execute_tapir(
            "SetGDLParametersOfElements",
            {"elementsWithGDLParameters": elements_with_params},
        )

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


def check_active_story(act_story: int, first_story: int, last_story: int,
                       gui_storey: str) -> tuple[bool, str]:
    """Czy aktywna kondygnacja AC pasuje do wyboru w GUI (czysta logika, bez AC).

    Mapowanie po INDEKSIE (nazwy story bywają puste): "parter" ↔ kondygnacja bazowa
    (firstStory); "poddasze" ↔ kondygnacja powyżej (idx > firstStory). Zwraca
    (ok, komunikat) — komunikat tylko gdy mismatch (ok=False).
    """
    if gui_storey == "poddasze":
        if last_story == first_story:
            return False, ("Projekt jednokondygnacyjny — nie ma poddasza. "
                           "Wybierz 'Parter' albo dodaj kondygnację w AC.")
        if act_story > first_story:
            return True, ""
        return False, (f"Aktywna kondygnacja AC = parter (idx {act_story}), "
                       f"a wybrałeś 'Poddasze'. Przełącz w AC kondygnację na poddasze "
                       f"(idx > {first_story}) i spróbuj ponownie.")
    # parter (domyślnie)
    if act_story == first_story:
        return True, ""
    return False, (f"Aktywna kondygnacja AC = idx {act_story}, a wybrałeś 'Parter' "
                   f"(idx {first_story}). Przełącz w AC kondygnację na parter.")
