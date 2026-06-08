"""RED-first: core/furniture_extractor — Furniture (Shapely box) -> AC library Object.

Mapowanie typ->obiekt biblioteczny (wybór Dawida 2026-06-08), kotwica=róg boxa,
wymiary=rozmiar boxa, reguła łóżek (master=podwójne / reszta=pojedyncze),
payload CreateObjects {libraryPartName, coordinates{x,y,z}, dimensions{x,y}}.
"""
import pytest
from shapely.geometry import box

from core.models import Room, RoomSpec, Strefa
from core.furniture import Furniture, FurnishResult
from core.furniture_extractor import (
    extract_furniture,
    furniture_to_tapir_payload,
    FurnitureObject,
    FURNITURE_LIBRARY_MAP,
    BED_DOUBLE,
    BED_SINGLE,
)


def _room(room_id: str, w: float, h: float, strefa: Strefa = Strefa.NOCNA) -> Room:
    spec = RoomSpec(id=room_id, nazwa=room_id, strefa=strefa,
                    wymaga_okna=False, priorytet_fasady=None)
    r = Room(spec=spec, polygon=box(0.0, 0.0, w, h))
    r.update_metrics()
    return r


def test_maps_sofa_to_library_part():
    f = Furniture("sofa", box(2.0, 3.0, 2.9, 5.4), "salon", "Sofa")
    objs = extract_furniture(FurnishResult([f], []), [])
    assert len(objs) == 1
    assert objs[0].library_part_name == "Sofa"


def test_object_uses_real_library_dims_centered_on_box():
    # box w layoucie 0.9×2.4, ale obiekt = REALNE wymiary Sofy z wyboru Dawida
    # (1.6×0.85), CENTROWANY na centroidzie boxa (zero rozciągania).
    f = Furniture("sofa", box(2.0, 3.0, 2.9, 5.4), "salon", "Sofa")  # centroid (2.45, 4.2)
    obj = extract_furniture(FurnishResult([f], []), [])[0]
    assert (obj.dim_x, obj.dim_y) == pytest.approx((1.6, 0.85))
    assert obj.x == pytest.approx(2.45 - 1.6 / 2)   # centroid.x - poł. realnej szer.
    assert obj.y == pytest.approx(4.2 - 0.85 / 2)   # centroid.y - poł. realnej głęb.


def test_master_bed_uses_real_double_bed_dimensions():
    syp = _room("sypialnia_1", 4.0, 3.0)
    bed = Furniture("bed", box(0, 0, 1.6, 2.0), "sypialnia_1", "Łóżko")
    obj = extract_furniture(FurnishResult([bed], []), [syp])[0]
    assert obj.library_part_name == BED_DOUBLE
    assert (obj.dim_x, obj.dim_y) == pytest.approx((1.8, 2.0))  # realne Łóżko podwójne 01


def test_master_bedroom_gets_double_bed_others_single():
    master = _room("sypialnia_1", 5.0, 4.0)   # 20 m² — większa
    second = _room("sypialnia_2", 3.0, 3.0)   #  9 m²
    bed_m = Furniture("bed", box(0, 0, 1.6, 2.0), "sypialnia_1", "Łóżko")
    bed_s = Furniture("bed", box(0, 0, 1.6, 2.0), "sypialnia_2", "Łóżko")
    objs = extract_furniture(FurnishResult([bed_m, bed_s], []), [master, second])
    by_room = {o.room_id: o.library_part_name for o in objs}
    assert by_room["sypialnia_1"] == BED_DOUBLE   # "Łóżko podwójne 01"
    assert by_room["sypialnia_2"] == BED_SINGLE   # "Łóżko 01"


def test_single_bedroom_bed_is_double():
    syp = _room("sypialnia_1", 4.0, 3.0)
    bed = Furniture("bed", box(0, 0, 1.6, 2.0), "sypialnia_1", "Łóżko")
    obj = extract_furniture(FurnishResult([bed], []), [syp])[0]
    assert obj.library_part_name == BED_DOUBLE


def test_unmapped_piece_type_is_skipped():
    # boiler/shelving nie zostały wybrane przez Dawida → brak w mapie → pomijamy
    f = Furniture("boiler", box(0, 0, 0.6, 0.8), "kotlownia", "Kocioł")
    objs = extract_furniture(FurnishResult([f], []), [])
    assert objs == []


def test_bathroom_fixtures_mapped():
    fs = [
        Furniture("bathtub", box(0, 0, 0.8, 1.7), "lazienka", "Wanna"),
        Furniture("washbasin", box(0, 0, 0.6, 0.5), "lazienka", "Umywalka"),
        Furniture("toilet", box(0, 0, 0.4, 0.6), "lazienka", "WC"),
    ]
    objs = extract_furniture(FurnishResult(fs, []), [])
    names = {o.piece_type: o.library_part_name for o in objs}
    assert names == {
        "bathtub": "Wanna",
        "washbasin": "Szafka z umywalką",
        "toilet": "WC",
    }


def test_payload_shape_matches_createobjects_schema():
    obj = FurnitureObject(
        library_part_name="Sofa", x=12.0, y=-30.0, z=0.0,
        dim_x=0.9, dim_y=2.4, piece_type="sofa", room_id="salon",
    )
    payload = furniture_to_tapir_payload([obj])
    assert payload == [{
        "libraryPartName": "Sofa",
        "coordinates": {"x": 12.0, "y": -30.0, "z": 0.0},
        "dimensions": {"x": 0.9, "y": 2.4},
    }]


def test_payload_has_no_angle_field():
    # CreateObjects ma additionalProperties:false i ODRZUCA 'angle'
    obj = FurnitureObject("Sofa", 0.0, 0.0, 0.0, 1.0, 1.0, "sofa", "salon")
    payload = furniture_to_tapir_payload([obj])[0]
    assert "angle" not in payload
    assert set(payload.keys()) == {"libraryPartName", "coordinates", "dimensions"}


def test_payload_applies_world_offset_to_coordinates_only():
    # meble mają współrzędne absolutne → offset jak ściany/etykiety; dimensions BEZ offsetu
    obj = FurnitureObject("Sofa", 2.0, 3.0, 0.0, 0.9, 2.4, "sofa", "salon")
    payload = furniture_to_tapir_payload([obj], offset=(10.0, -5.0))[0]
    assert payload["coordinates"]["x"] == pytest.approx(12.0)
    assert payload["coordinates"]["y"] == pytest.approx(-2.0)
    assert payload["coordinates"]["z"] == pytest.approx(0.0)
    assert payload["dimensions"] == {"x": 0.9, "y": 2.4}


def test_mapping_covers_all_selected_types():
    # twardy kontrakt na wybór Dawida — te typy MUSZĄ być zmapowane
    for t in ["bed", "nightstand", "wardrobe", "sofa", "coffee_table",
              "tv_unit", "kitchen_counter", "dining_table",
              "bathtub", "washbasin", "toilet", "basin"]:
        assert t in FURNITURE_LIBRARY_MAP, f"brak mapowania dla {t}"
