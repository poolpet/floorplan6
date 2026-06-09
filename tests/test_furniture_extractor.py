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
    furniture_to_create_payload,
    furniture_to_gdl_payload,
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


def test_object_mirrors_solver_box_exactly():
    # AC odwzorowuje box solvera 1:1: kotwica = lewy-dolny róg boxa, A/B = wymiary boxa.
    # Renderer rysuje TEN box (zaakceptowany przez Dawida) → AC ma być identyczny.
    # Zero re-derywacji (_orient_to_box/_anchor) — to one rozjeżdżały pozycję/skalę.
    f = Furniture("sofa", box(2.0, 3.0, 3.6, 3.85), "salon", "Sofa")  # 1.6×0.85 przy ścianie
    obj = extract_furniture(FurnishResult([f], []), [])[0]
    assert obj.library_part_name == "Sofa"
    assert (obj.x, obj.y) == pytest.approx((2.0, 3.0))             # lewy-dolny róg boxa
    assert (obj.dim_x, obj.dim_y) == pytest.approx((1.6, 0.85))    # wymiary boxa WPROST


def test_vertical_box_gives_tall_object_no_swap():
    # Box pionowy (sofa długą osią w pionie przy ścianie W): A/B = wymiary boxa WPROST
    # (0.9×2.4), BEZ zamiany — box już koduje orientację. Rotacja symbolu niedostępna,
    # ale footprint = box = renderer (to było rozjeżdżane przez _orient_to_box).
    f = Furniture("sofa", box(0.1, 1.0, 1.0, 3.4), "salon", "Sofa")  # 0.9×2.4
    obj = extract_furniture(FurnishResult([f], []), [])[0]
    assert (obj.x, obj.y) == pytest.approx((0.1, 1.0))
    assert (obj.dim_x, obj.dim_y) == pytest.approx((0.9, 2.4))


def test_coffee_table_mirrors_box_not_recentered():
    # Stolik też 1:1 z boxem (solver postawił go w środku — nie ruszamy, nie centrujemy).
    f = Furniture("coffee_table", box(2.0, 2.0, 2.7, 2.7), "salon", "Stolik")
    obj = extract_furniture(FurnishResult([f], []), [])[0]
    assert (obj.x, obj.y) == pytest.approx((2.0, 2.0))
    assert (obj.dim_x, obj.dim_y) == pytest.approx((0.7, 0.7))


def test_master_bed_name_double_dims_from_box():
    # Nazwa wg reguły master (podwójne), ale WYMIARY z boxa solvera (nie sztywne z mapy).
    syp = _room("sypialnia_1", 4.0, 3.0)
    bed = Furniture("bed", box(0, 0, 1.6, 2.0), "sypialnia_1", "Łóżko")
    obj = extract_furniture(FurnishResult([bed], []), [syp])[0]
    assert obj.library_part_name == BED_DOUBLE
    assert (obj.dim_x, obj.dim_y) == pytest.approx((1.6, 2.0))  # z boxa solvera


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


def test_create_payload_omits_dimensions_ac_reads_them_as_ratio():
    # AC czyta CreateObjects.dimensions jako MNOŻNIK domyślnego A/B (nie metry, źródło
    # Tapir ElementCreationCommands.cpp) → create NIE wysyła dimensions; realny rozmiar
    # ustawiamy potem przez A/B (SetGDLParametersOfElements).
    obj = FurnitureObject(
        library_part_name="Sofa", x=12.0, y=-30.0, z=0.0,
        dim_x=0.9, dim_y=2.4, piece_type="sofa", room_id="salon",
    )
    payload = furniture_to_create_payload([obj])
    assert payload == [{
        "libraryPartName": "Sofa",
        "coordinates": {"x": 12.0, "y": -30.0, "z": 0.0},
    }]
    assert "dimensions" not in payload[0]


def test_create_payload_has_no_angle_field():
    # CreateObjects ma additionalProperties:false i ODRZUCA 'angle'
    obj = FurnitureObject("Sofa", 0.0, 0.0, 0.0, 1.0, 1.0, "sofa", "salon")
    payload = furniture_to_create_payload([obj])[0]
    assert "angle" not in payload
    assert set(payload.keys()) == {"libraryPartName", "coordinates"}


def test_create_payload_applies_world_offset_to_coordinates():
    # meble mają współrzędne absolutne → offset jak ściany/etykiety
    obj = FurnitureObject("Sofa", 2.0, 3.0, 0.0, 0.9, 2.4, "sofa", "salon")
    payload = furniture_to_create_payload([obj], offset=(10.0, -5.0))[0]
    assert payload["coordinates"]["x"] == pytest.approx(12.0)
    assert payload["coordinates"]["y"] == pytest.approx(-2.0)
    assert payload["coordinates"]["z"] == pytest.approx(0.0)


def test_gdl_payload_sets_A_B_in_meters_from_oriented_dims():
    # realny rozmiar w metrach: A = oś X (dim_x), B = oś Y (dim_y) — payload SetGDL.
    obj = FurnitureObject("Sofa", 2.0, 3.0, 0.0, 1.6, 0.85, "sofa", "salon")
    payload = furniture_to_gdl_payload([obj], ["GUID-1"])
    assert payload == [{
        "elementId": {"guid": "GUID-1"},
        "gdlParameters": [
            {"name": "A", "value": 1.6},
            {"name": "B", "value": 0.85},
        ],
    }]


def test_kitchen_counter_expands_to_fridge_plus_base_cabinets():
    # Kuchnia z POJEDYNCZYCH mebli (wybór Dawida 2026-06-09): blat (kitchen_counter box)
    # → rząd modułów 0.6 m: 1 lodówka + N szafek dolnych. Bieg 2.4 m → 4 moduły = lodówka+3.
    room = _room("salon_aneks", 6.0, 5.0, Strefa.DZIENNA)
    f = Furniture("kitchen_counter", box(0.1, 0.1, 2.5, 0.7), "salon_aneks", "Blat")  # 2.4×0.6
    objs = extract_furniture(FurnishResult([f], []), [room])
    names = [o.library_part_name for o in objs]
    assert len(objs) == 4
    assert names.count("Lodówka") == 1
    assert names.count("Szafka podstawowa") == 3


def test_kitchen_pieces_in_a_row_along_horizontal_wall():
    room = _room("salon_aneks", 6.0, 5.0, Strefa.DZIENNA)
    f = Furniture("kitchen_counter", box(0.0, 0.0, 2.4, 0.6), "salon_aneks", "Blat")
    objs = extract_furniture(FurnishResult([f], []), [room])
    assert sorted(o.x for o in objs) == pytest.approx([0.0, 0.6, 1.2, 1.8])  # moduły co 0.6 wzdłuż X
    for o in objs:
        assert o.y == pytest.approx(0.0)        # wszystkie przy dolnej krawędzi biegu
        assert o.dim_x == pytest.approx(0.6)    # moduł wzdłuż ściany (X)


def test_kitchen_vertical_run_stacks_along_Y_with_swapped_dims():
    # Pionowy bieg (ściana W/E): moduły układają się wzdłuż Y, głębokość wzdłuż X
    # (orientacja przez swap dim_x/dim_y — działa dla pojedynczych obiektów).
    room = _room("salon_aneks", 5.0, 6.0, Strefa.DZIENNA)
    f = Furniture("kitchen_counter", box(0.0, 0.0, 0.58, 2.4), "salon_aneks", "Blat")  # pionowy
    objs = extract_furniture(FurnishResult([f], []), [room])
    assert sorted(o.y for o in objs) == pytest.approx([0.0, 0.6, 1.2, 1.8])
    for o in objs:
        assert o.dim_x == pytest.approx(0.58)   # głębokość wzdłuż X
        assert o.dim_y == pytest.approx(0.6)    # moduł wzdłuż ściany (Y)


def test_kitchen_pieces_get_normal_AB_no_composite():
    # Szafka/lodówka to ZWYKŁE obiekty → dostają A/B w metrach (ścieżka która działa),
    # BEZ żadnego composite (iLayoutType itd. — koniec z `Zestaw mebli kuchennych`).
    cab = FurnitureObject("Szafka podstawowa", 0, 0, 0, 0.6, 0.58, "base_cabinet", "salon_aneks")
    payload = furniture_to_gdl_payload([cab], ["G"])
    params = {p["name"]: p["value"] for p in payload[0]["gdlParameters"]}
    assert params == {"A": 0.6, "B": 0.58}


def test_kitchenette_assigns_sink_and_cooktop_to_different_cabinets():
    # minimum kuchni: lodówka + szafki, gdzie JEDNA ma zlew, JEDNA płytę (reszta sam blat) —
    # wyposażenie przez flagi bSink/bCooktop na "Szafce podstawowej" (wybór Dawida 2026-06-09).
    room = _room("salon_aneks", 6.0, 5.0, Strefa.DZIENNA)
    f = Furniture("kitchen_counter", box(0.0, 0.0, 3.0, 0.6), "salon_aneks", "Blat")  # 5 modułów
    objs = extract_furniture(FurnishResult([f], []), [])
    cabs = [o for o in objs if o.piece_type == "base_cabinet"]
    extra = [dict(o.gdl_extra) for o in cabs]
    assert sum(1 for e in extra if e.get("bSink")) == 1       # dokładnie jedna szafka ze zlewem
    assert sum(1 for e in extra if e.get("bCooktop")) == 1    # dokładnie jedna z płytą
    sink_i = next(i for i, e in enumerate(extra) if e.get("bSink"))
    cook_i = next(i for i, e in enumerate(extra) if e.get("bCooktop"))
    assert sink_i != cook_i                                   # różne szafki
    assert all(e.get("bCounter") for e in extra)              # każda szafka ma blat


def test_kitchen_cabinet_gdl_payload_includes_equipment():
    cab = FurnitureObject("Szafka podstawowa", 0, 0, 0, 0.6, 0.58, "base_cabinet", "salon_aneks",
                          gdl_extra=(("bCounter", True), ("bSink", True), ("bCooktop", False)))
    payload = furniture_to_gdl_payload([cab], ["G"])
    params = {p["name"]: p["value"] for p in payload[0]["gdlParameters"]}
    assert params["A"] == 0.6 and params["B"] == 0.58
    assert params["bCounter"] is True
    assert params["bSink"] is True
    assert params["bCooktop"] is False


def test_gdl_payload_aligns_objects_with_guids_by_index():
    a = FurnitureObject("Sofa", 0, 0, 0, 1.6, 0.85, "sofa", "salon")
    b = FurnitureObject("WC", 0, 0, 0, 0.35, 0.64, "toilet", "lazienka")
    payload = furniture_to_gdl_payload([a, b], ["GA", "GB"])
    assert payload[0]["elementId"]["guid"] == "GA"
    assert payload[1]["elementId"]["guid"] == "GB"
    assert payload[1]["gdlParameters"] == [
        {"name": "A", "value": 0.35}, {"name": "B", "value": 0.64}]


def test_gdl_payload_empty_when_guid_count_mismatches_objects():
    # length mismatch = AC pominęło którąś część (zła nazwa) → index-alignment niepewny
    # dla WSZYSTKICH → nie ryzykuj cudzego A/B, zwróć [] (SET pominięty całkowicie).
    a = FurnitureObject("Sofa", 0, 0, 0, 1.6, 0.85, "sofa", "salon")
    b = FurnitureObject("WC", 0, 0, 0, 0.35, 0.64, "toilet", "lazienka")
    assert furniture_to_gdl_payload([a, b], ["GA"]) == []


def test_mapping_covers_all_selected_types():
    # twardy kontrakt na wybór Dawida — te typy MUSZĄ być zmapowane
    for t in ["bed", "nightstand", "wardrobe", "sofa", "coffee_table",
              "tv_unit", "kitchen_counter", "dining_table",
              "bathtub", "washbasin", "toilet", "basin"]:
        assert t in FURNITURE_LIBRARY_MAP, f"brak mapowania dla {t}"
