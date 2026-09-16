"""Mapowanie polskich nazw pokoi/szablonów na angielskie (`bridge/room_names.py`).

`core/` jest zamrożone — nazwy w `templates/*.json` zostają polskie (są też
identyfikatorami dla solvera). Tester bety widzi je w Archicadzie (nazwa strefy,
etykieta) i w podglądzie, więc KAŻDA nazwa z szablonów musi mieć angielski odpowiednik.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bridge.room_names import ROOM_NAMES_EN, room_name_en

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = sorted((ROOT / "templates").glob("*.json"))
POLISH = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")


def _template_names() -> list[tuple[str, str]]:
    """[(plik, nazwa)] — nazwa szablonu i każdego pokoju w nim."""
    out: list[tuple[str, str]] = []
    for path in TEMPLATES:
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((path.name, data["nazwa"]))
        for room in data["pokoje"]:
            out.append((path.name, room["nazwa"]))
    return out


def test_templates_are_found():
    assert len(TEMPLATES) >= 10, "brak szablonów — test niczego by nie sprawdzał"


@pytest.mark.parametrize("src,name", _template_names(), ids=lambda v: str(v)[:40])
def test_every_template_name_resolves_to_english(src, name):
    en = room_name_en(name)
    assert not POLISH.search(en), f"{src}: {name!r} -> {en!r} nadal po polsku"


def test_passthrough_for_unknown_name():
    assert room_name_en("Totally Unknown Room") == "Totally Unknown Room"
    assert room_name_en("") == ""


def test_english_names_pass_through_unchanged():
    """Szablony mieszkań są już po angielsku — mapowanie nie może ich psuć."""
    for name in ("Bathroom", "Master bedroom", "Room / Bedroom 2", "WC"):
        assert room_name_en(name) == name


def test_storey_words():
    assert room_name_en("parter") == "Ground floor"
    assert room_name_en("poddasze") == "Attic"
    assert room_name_en("piętro") == "First floor"
    assert room_name_en("PARTER") == "GROUND FLOOR"
    assert room_name_en("PODDASZE") == "ATTIC"
    assert room_name_en("PIĘTRO") == "FIRST FLOOR"


def test_mapping_values_are_all_english():
    bad = {k: v for k, v in ROOM_NAMES_EN.items() if POLISH.search(v)}
    assert not bad, bad


class _FakeTapir:
    """Zapamiętuje payloady zamiast gadać z Archicadem."""

    def __init__(self):
        self.zones = []
        self.labels = []

    def create_zones(self, zones):
        self.zones = zones
        return [f"guid-{i}" for i, _ in enumerate(zones)]

    def create_labels(self, labels):
        self.labels = labels
        return [f"lbl-{i}" for i, _ in enumerate(labels)]


def _polish_plan():
    from shapely.geometry import box
    from core.models import (Boundary, EdgeInfo, FloorPlan, Orientation, Room,
                             RoomSpec, Strefa, Template, WallType)

    def room(rid, nazwa, strefa, x):
        spec = RoomSpec(id=rid, nazwa=nazwa, strefa=strefa,
                        wymaga_okna=False, priorytet_fasady=None)
        r = Room(spec=spec, polygon=box(x, 0, x + 3, 3))
        r.update_metrics()
        return r

    boundary = Boundary(
        polygon=box(0, 0, 6, 3),
        edges=[EdgeInfo(start=(0, 0), end=(6, 0),
                        wall_type=WallType.FACADE, orientation=Orientation.S)],
        entry_point=(3.0, 0.0),
    )
    rooms = [room("kuchnia", "Kuchnia", Strefa.USLUGOWA, 0),
             room("salon", "Salon", Strefa.DZIENNA, 3)]
    template = Template(id="house_parter", nazwa="Dom jednorodzinny — parter",
                        typ_mieszkania="DOM_PARTER",
                        pokoje=[r.spec for r in rooms], sasiedztwo=[])
    return FloorPlan(boundary=boundary, template=template, rooms=rooms)


def test_export_writes_english_zone_names_and_labels():
    """Szew eksportu: nazwa strefy i tekst etykiety wychodzą do AC po angielsku."""
    from bridge.plan_writer import export_plan_to_archicad

    tapir = _FakeTapir()
    export_plan_to_archicad(
        _polish_plan(), tapir=tapir, include_walls=False, include_doors=False,
        include_windows=False, include_furniture=False, apartment_id="DOM-PARTER",
    )
    assert [z["name"] for z in tapir.zones] == ["Kitchen", "Living room"]
    assert [lbl["text"].split("\n")[0] for lbl in tapir.labels] == ["Kitchen", "Living room"]
    # Powierzchnia w drugiej linii etykiety zostaje nietknięta.
    assert all(lbl["text"].split("\n")[1].endswith("m²") for lbl in tapir.labels)
