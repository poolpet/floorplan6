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

import logging
import os
import time
from typing import List, Optional, Tuple

from archicad import ACConnection

logger = logging.getLogger(__name__)

ARCHICAD_PORT_START = 19723
ARCHICAD_PORT_RANGE = 8                # scan 19723..19730
CONNECT_RETRIES = 3
CONNECT_DELAY_S = 2.0
TAPIR_NAMESPACE = "FloorForgeCommand"


def _env_ac_port() -> Optional[int]:
    """Port JSON instancji AC przekazany przez add-on (FLOORFORGE_AC_PORT). None gdy brak/niepoprawny."""
    raw = os.environ.get("FLOORFORGE_AC_PORT", "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        logger.warning("FLOORFORGE_AC_PORT niepoprawny: %r", raw)
        return None
    if not (1 <= port <= 65535):
        logger.warning("FLOORFORGE_AC_PORT poza zakresem: %s", port)
        return None
    return port


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
                f"No Archicad instance is responding on ports "
                f"{ARCHICAD_PORT_START}..{ARCHICAD_PORT_START + ARCHICAD_PORT_RANGE - 1}. "
                f"Check that Archicad is running with the FloorForge add-on installed."
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
          0. Jeśli add-on podał port w FLOORFORGE_AC_PORT — użyj go bez skanu.
          1. Jeśli mamy zapisany ostatni działający port — spróbuj tam.
          2. W przeciwnym razie skanuj 19723..19730 i wybierz tę z zaznaczeniem.
        """
        env_port = _env_ac_port()
        if env_port is not None:
            conn = self._try_connect(env_port)
            if conn is not None:
                self._active_port = env_port
                self._conn = conn
                logger.info("connect: port z FLOORFORGE_AC_PORT=%s", env_port)
                return True
            logger.warning("connect: FLOORFORGE_AC_PORT=%s nie odpowiada — skanuję porty", env_port)

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
            "Archicad is not responding on any of the scanned ports."
        )

    @classmethod
    def list_instances(cls, port_range=None) -> list[dict]:
        """Wykryte instancje AC: [{port, projectName, projectPath}] (deterministyczny picker).

        Świeże połączenie per port (NIE mutuje singletona), nazwa via Tapir GetProjectInfo.
        Martwy port pominięty; brak nazwy → "(unknown)".
        """
        if port_range is None:
            port_range = range(ARCHICAD_PORT_START,
                               ARCHICAD_PORT_START + ARCHICAD_PORT_RANGE)
        out: List[dict] = []
        for port in port_range:
            conn = cls._try_connect(port)
            if conn is None:
                continue
            name, path = "(unknown)", ""
            try:
                cid = conn.types.AddOnCommandId(TAPIR_NAMESPACE, "GetProjectInfo")
                info = conn.commands.ExecuteAddOnCommand(cid, {}) or {}
                name = info.get("projectName") or "(unknown)"
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
                f"Archicad on port {port} is not responding (FloorForge add-on?)."
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

    # Kandydaci na kształt param ChangeWindow (kolejność = notebooks/ac_story_switch_probe.py).
    # Zwycięzca z live-testu przesuwany na początek listy.
    CHANGE_WINDOW_SHAPES = [
        ("navigatorItemId:{guid}",      lambda g: {"navigatorItemId": {"guid": g}}),
        ("navigatorItemId:{guid,type}", lambda g: {"navigatorItemId": {"guid": g, "type": "StoryItem"}}),
        ("{guid}",                      lambda g: {"guid": g}),
        ("databaseId+FloorPlan",        lambda g: {"databaseId": {"guid": g}, "windowType": "FloorPlan"}),
    ]

    def story_navitems(self) -> dict[int, str]:
        """Indeks kondygnacji AC → navigatorItemId.guid.

        ProjectMap listuje story top-down, więc reversed = indeksy rosnące. Klucze są
        w PRZESTRZENI INDEKSÓW AC (`GetStories.firstStory`, ta sama co `actStory`) —
        przy piwnicy `firstStory == -1` parter ma indeks 0, nie 1.
        """
        first = int((self.get_stories() or {}).get("firstStory", 0))
        tree_id = self.types.NavigatorTreeId(type="ProjectMap")
        tree = self.commands.GetNavigatorItemTree(tree_id)
        guids_top_down: list[str] = []

        def walk(node):
            item = getattr(node, "navigatorItem", node)
            nid = getattr(getattr(item, "navigatorItemId", None), "guid", None)
            if getattr(item, "type", None) == "StoryItem" and nid:
                guids_top_down.append(str(nid))
            for ch in (getattr(item, "children", None) or []):
                walk(ch)

        walk(getattr(tree, "rootItem", tree))
        return {first + i: g for i, g in enumerate(reversed(guids_top_down))}

    def activate_story(self, target_index: int) -> bool:
        """Ustaw aktywną kondygnację AC na `target_index`. True gdy GetStories.actStory == target."""
        st = self.get_stories() or {}
        if int(st.get("actStory", -1)) == target_index:
            return True
        guid = self.story_navitems().get(target_index)
        if guid is None:
            logger.warning("activate_story: brak nav-itemu dla story %s", target_index)
            return False
        for label, build in self.CHANGE_WINDOW_SHAPES:
            try:
                self._execute_tapir("ChangeWindow", build(guid))
            except Exception as e:
                logger.info("activate_story: kształt %s odrzucony: %r", label, e)
                continue
            now = int((self.get_stories() or {}).get("actStory", -1))
            if now == target_index:
                logger.info("activate_story: OK kształt=%s → actStory=%s", label, now)
                return True
        logger.warning("activate_story: żaden kształt nie przełączył na %s", target_index)
        return False

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
            print("[get_all_walls] 0 walls on the active storey/window "
                  "(GetElementsByType = scope of the active plan database) — windows skipped. "
                  "Check that the active Archicad window is the plan of the right storey.")
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


def parter_story_index(first_story: int, last_story: int) -> int:
    """Indeks parteru w przestrzeni indeksów AC — JEDNO źródło prawdy.

    Parter to indeks 0, o ile taka kondygnacja w projekcie istnieje: przy piwnicy
    `firstStory = -1`, a parter leży o jeden wyżej (NIE na `firstStory`). Dopiero
    gdy projekt w ogóle nie obejmuje indeksu 0 (np. zaczyna się od 1), parterem
    jest kondygnacja bazowa `firstStory`.

    Używane zarówno przez `check_active_story` (ostrzeżenie), jak i przez ścieżkę
    eksportu w GUI (auto-przełączanie) — obie muszą wskazywać tę samą kondygnację.
    """
    return 0 if first_story <= 0 <= last_story else first_story


def check_active_story(act_story: int, first_story: int, last_story: int,
                       gui_storey: str) -> tuple[bool, str]:
    """Czy aktywna kondygnacja AC pasuje do wyboru w GUI (czysta logika, bez AC).

    Mapowanie po INDEKSIE (nazwy story bywają puste): "parter" ↔
    `parter_story_index(first, last)`; "poddasze" ↔ kondygnacja bezpośrednio nad
    parterem lub wyżej. Zwraca (ok, komunikat) — komunikat tylko gdy mismatch
    (ok=False).
    """
    parter_idx = parter_story_index(first_story, last_story)
    poddasze_idx = parter_idx + 1
    if gui_storey == "poddasze":
        if poddasze_idx > last_story:
            return False, (f"The project has no storey above the ground floor "
                           f"(idx {poddasze_idx}) — there is no attic. Select 'Ground floor' "
                           f"or add a storey in Archicad.")
        if act_story >= poddasze_idx:
            return True, ""
        return False, (f"The active Archicad storey = idx {act_story}, but you selected "
                       f"'Attic' (idx {poddasze_idx}). Switch the storey in Archicad "
                       f"to the attic and try again.")
    # parter (domyślnie)
    if act_story == parter_idx:
        return True, ""
    return False, (f"The active Archicad storey = idx {act_story}, but you selected "
                   f"'Ground floor' (idx {parter_idx}). Switch the storey in Archicad "
                   f"to the ground floor.")
