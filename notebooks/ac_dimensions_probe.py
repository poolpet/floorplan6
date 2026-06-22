"""SONDA wymiarów/parametryczności (opcja B = pełne BIM) — rozstrzyga na ŻYWYM AC:

  1. Czy `GetGDLParametersOfElements` i `SetGDLParametersOfElements` DZIAŁAJĄ w tym
     buildzie Tapira (próba + readback).
  2. Czy `SetGDLParametersOfElements(A,B)` REALNIE zmienia rozmiar wstawionego obiektu
     w 2D — mierzymy `dimensions{x,y,z}` z GetDetailsOfElements PRZED i PO ustawieniu A/B.
     To jest mechanizm, na którym stoi cała opcja B. Jeśli rozmiar się zmienia → B działa.
  3. Potwierdza (tanio) że `dimensions` w CreateObjects to MNOŻNIK domyślnego A/B, nie metry
     — wstawia tę samą część 2× przy dimensions {1,1} i {2,1}, porównuje odczytany rozmiar.
  4. WYKRYWA parametry: zrzuca pełną listę paramów GDL `Zestaw mebli kuchennych` (czy w
     ogóle ma param długości?) ORAZ każdego obiektu, który ZAZNACZYSZ przed uruchomieniem
     — żeby poznać DOKŁADNĄ nazwę parametrycznego blatu/szafki Casework + nazwę paramu
     sterującego długością (A vs param-specyficzny).

Schematy komend (ze źródła Tapira ENZYME-APD `ElementGDLParameterCommands.cpp`):
  GET:  {"elements":[{"elementId":{"guid":G}}]} -> {"gdlParametersOfElements":[<lista paramów>]}
        param = {name, displayName, index, type(Length/RealNumber/Integer/...), value, ...}
  SET:  {"elementsWithGDLParameters":[{"elementId":{"guid":G},
                                       "gdlParameters":[{"name":"A","value":2.0}]}]}
        -> {"executionResults":[{success:bool, ...}]}

Uruchom z AC + Tapir. OPCJONALNIE: najpierw ZAZNACZ w AC parametryczny blat/szafkę
kuchenną (Casework), żebym poznał jej nazwę i parametry. Potem:
    PYTHONPATH=. venv/bin/python notebooks/ac_dimensions_probe.py

Po uruchomieniu: wklej mi CAŁY wydruk.
"""
from __future__ import annotations

import json

from core.furniture_extractor import BED_DOUBLE

# Części z biblioteki Dawida (AC29) do testu zmiany rozmiaru przez A/B.
PARTS_TO_TEST = ["Sofa", BED_DOUBLE, "Zestaw mebli kuchennych"]

# Współrzędne testowe — daleko od geometrii, rozstawione, łatwe do znalezienia/skasowania.
BASE_X, BASE_Y = 30.0, 30.0
DX_BETWEEN = 4.0

# Wartości A/B do wymuszenia (metry). Wyraźnie inne niż typowe domyślne → łatwo zobaczyć zmianę.
SET_A, SET_B = 2.0, 1.0


def _execute(tapir, name, params):
    """Surowe wykonanie komendy Tapir + złap wyjątek (uczymy się dostępności)."""
    try:
        return tapir._execute_tapir(name, params), None
    except Exception as e:  # noqa: BLE001 — probe ma pokazać każdy błąd
        return None, repr(e)


def _get_gdl_params(tapir, guid):
    """Zwróć (lista_paramów, surowy_wynik, błąd)."""
    res, err = _execute(tapir, "GetGDLParametersOfElements",
                        {"elements": [{"elementId": {"guid": guid}}]})
    if err is not None:
        return [], None, err
    lst = (res or {}).get("gdlParametersOfElements", [])
    entry = lst[0] if lst else {}
    # Tolerancja: entry może być listą paramów albo dict z "parameters".
    if isinstance(entry, dict):
        params = entry.get("parameters", entry.get("gdlParameters", []))
    elif isinstance(entry, list):
        params = entry
    else:
        params = []
    return params, res, None


def _set_gdl_params(tapir, guid, name_value_pairs):
    """name_value_pairs = [("A", 2.0), ("B", 1.0)] -> wykonaj SET, zwróć (wynik, błąd)."""
    gdl = [{"name": n, "value": v} for n, v in name_value_pairs]
    return _execute(tapir, "SetGDLParametersOfElements",
                    {"elementsWithGDLParameters": [
                        {"elementId": {"guid": guid}, "gdlParameters": gdl}]})


def _details(tapir, guid):
    """Zwróć (dims(x,y,z) lub None, libPart_name lub '?', angle lub None, surowy)."""
    det = tapir.get_element_details([guid])
    if not det or not isinstance(det[0], dict):
        return None, "?", None, det
    inner = det[0].get("details", det[0])
    dims = inner.get("dimensions")
    dxyz = None
    if isinstance(dims, dict):
        dxyz = (dims.get("x"), dims.get("y"), dims.get("z"))
    libpart = inner.get("libPart", inner.get("libraryPart", {}))
    name = libpart.get("name") if isinstance(libpart, dict) else "?"
    return dxyz, name, inner.get("angle"), det[0]


def _fmt_dims(d):
    if not d:
        return "(brak dimensions w details)"
    x, y, z = d
    def f(v):
        return f"{v:.3f}" if isinstance(v, (int, float)) else str(v)
    return f"x={f(x)} y={f(y)} z={f(z)}"


def _print_params(params, highlight=("A", "B", "ZZYZX")):
    """Wypisz param y; wyróżnij A/B/ZZYZX oraz wszystkie typu Length."""
    if not params:
        print("    (pusta lista paramów)")
        return
    print(f"    {len(params)} paramów. Wyróżnione + wszystkie 'Length':")
    by_name = {}
    for p in params:
        if not isinstance(p, dict):
            continue
        nm = p.get("name", "?")
        by_name[nm] = p
        is_len = str(p.get("type", "")).lower() == "length"
        if nm in highlight or is_len:
            print(f"      • {nm:10s} type={p.get('type','?'):10s} "
                  f"value={p.get('value')}  ({p.get('displayName','')})")
    missing = [h for h in highlight if h not in by_name]
    if missing:
        print(f"    UWAGA: brak paramów {missing} w tej części.")
    return by_name


def _resize_test(tapir, part_name, x, y, created):
    print(f"\n=== ZMIANA ROZMIARU przez A/B: '{part_name}' @ ({x},{y}) ===")
    guids = tapir.create_objects([{
        "libraryPartName": part_name,
        "coordinates": {"x": x, "y": y, "z": 0.0},
    }])
    if not guids:
        print(f"  ✗ nie wstawiono '{part_name}' (zła nazwa? sprawdź w bibliotece).")
        return
    g = guids[0]
    created.append(g)
    print(f"  wstawiono guid={g} (rozmiar domyślny biblioteczny)")

    dims_before, libname, ang, _ = _details(tapir, g)
    print(f"  libPart='{libname}' angle={ang}")
    print(f"  dimensions PRZED: {_fmt_dims(dims_before)}")

    params, _, gerr = _get_gdl_params(tapir, g)
    if gerr is not None:
        print(f"  ✗ GetGDLParametersOfElements BŁĄD: {gerr}")
        print("    → ta komenda może być niedostępna w buildzie. To blokuje opcję B.")
        return
    by_name = _print_params(params) or {}

    # Ustaw A/B jeśli istnieją; inaczej pierwsze dwa parametry typu Length.
    to_set = []
    if "A" in by_name and "B" in by_name:
        to_set = [("A", SET_A), ("B", SET_B)]
    else:
        length_names = [p.get("name") for p in params
                        if isinstance(p, dict) and str(p.get("type", "")).lower() == "length"]
        if length_names:
            to_set = [(length_names[0], SET_A)]
            if len(length_names) > 1:
                to_set.append((length_names[1], SET_B))
    if not to_set:
        print("  (brak A/B ani paramów Length do ustawienia — nic nie zmieniam)")
        return

    print(f"  SET {to_set} ...")
    sres, serr = _set_gdl_params(tapir, g, to_set)
    if serr is not None:
        print(f"  ✗ SetGDLParametersOfElements BŁĄD: {serr}")
        print("    → komenda niedostępna LUB zły payload. To blokuje opcję B.")
        return
    exec_ok = None
    if isinstance(sres, dict):
        ex = sres.get("executionResults", [])
        if ex and isinstance(ex[0], dict):
            exec_ok = ex[0].get("success")
    print(f"  executionResults.success = {exec_ok}")

    dims_after, _, _, _ = _details(tapir, g)
    print(f"  dimensions PO:    {_fmt_dims(dims_after)}")
    if dims_before and dims_after:
        try:
            changed = (abs((dims_before[0] or 0) - (dims_after[0] or 0)) > 0.01 or
                       abs((dims_before[1] or 0) - (dims_after[1] or 0)) > 0.01)
        except TypeError:
            changed = None
        if changed is True:
            print("  ✅ ROZMIAR ZMIENIONY → SetGDLParametersOfElements DZIAŁA dla tej części (opcja B OK).")
        elif changed is False:
            print("  ❌ rozmiar BEZ ZMIAN → ta część IGNORUJE A/B (fixed symbol) → dla niej Slab/Morph.")
        else:
            print("  ? nie umiem porównać (dimensions niepełne).")


def _ratio_sanity(tapir, created):
    print("\n=== SANITY: dimensions w CreateObjects = MNOŻNIK (nie metry)? ===")
    part = "Sofa"
    a = tapir.create_objects([{"libraryPartName": part,
                               "coordinates": {"x": 30.0, "y": 40.0, "z": 0.0},
                               "dimensions": {"x": 1.0, "y": 1.0}}])
    b = tapir.create_objects([{"libraryPartName": part,
                               "coordinates": {"x": 34.0, "y": 40.0, "z": 0.0},
                               "dimensions": {"x": 2.0, "y": 1.0}}])
    if not a or not b:
        print(f"  (nie wstawiono '{part}' x2 — pomijam sanity)")
        return
    created.extend(a + b)
    da, _, _, _ = _details(tapir, a[0])
    db, _, _, _ = _details(tapir, b[0])
    print(f"  dimensions {{1,1}}: {_fmt_dims(da)}")
    print(f"  dimensions {{2,1}}: {_fmt_dims(db)}")
    if da and db and isinstance(da[0], (int, float)) and isinstance(db[0], (int, float)) and da[0]:
        ratio = db[0] / da[0]
        print(f"  stosunek x ({db[0]:.3f}/{da[0]:.3f}) = {ratio:.2f}  "
              f"→ ~2.0 potwierdza: dimensions = MNOŻNIK domyślnego A.")


def _dump_selection(tapir):
    print("\n=== ZRZUT ZAZNACZENIA (wykrycie blatu Casework) ===")
    sel = tapir.get_selected_elements()
    if not sel:
        print("  (brak zaznaczenia — jeśli chcesz, zaznacz parametryczny blat/szafkę")
        print("   kuchenną w AC i uruchom ponownie; zrzucę jej nazwę + parametry.)")
        return
    guids = []
    for e in sel:
        eid = e.get("elementId", e) if isinstance(e, dict) else e
        g = eid.get("guid") if isinstance(eid, dict) else str(eid)
        if g:
            guids.append(g)
    print(f"  zaznaczono {len(guids)} elem.")
    for g in guids:
        dims, libname, ang, _ = _details(tapir, g)
        print(f"\n  --- {libname} (guid {g}) angle={ang} dims={_fmt_dims(dims)} ---")
        params, _, gerr = _get_gdl_params(tapir, g)
        if gerr is not None:
            print(f"    GetGDLParametersOfElements błąd: {gerr}")
            continue
        # pełny zrzut paramów (krótko) + wyróżnienie Length
        for p in params:
            if not isinstance(p, dict):
                continue
            t = str(p.get("type", ""))
            mark = " ◀ LENGTH" if t.lower() == "length" else ""
            print(f"    {p.get('name','?'):14s} {t:10s} = {p.get('value')}"
                  f"  [{p.get('displayName','')}]{mark}")


def main():
    print("SONDA wymiarów/parametryczności — łączę z ArchiCAD ...")
    try:
        from bridge.tapir_connection import TapirConnection
    except Exception as e:
        print(f"BŁĄD importu bridge: {e!r}")
        return
    tapir = TapirConnection()
    try:
        tapir.connect()
        print(f"  Połączono na porcie {tapir.active_port}")
    except Exception as e:
        print(f"BŁĄD połączenia: {e!r}  → ArchiCAD + Tapir włączone?")
        return

    # 0) Zrzut zaznaczenia NAJPIERW (zanim cokolwiek wstawimy/zmienimy w zaznaczeniu).
    _dump_selection(tapir)

    created: list[str] = []
    # 1) Test zmiany rozmiaru przez A/B dla znanych części.
    for i, part in enumerate(PARTS_TO_TEST):
        _resize_test(tapir, part, BASE_X + i * DX_BETWEEN, BASE_Y, created)

    # 2) Sanity: dimensions = mnożnik.
    _ratio_sanity(tapir, created)

    # 3) Sprzątanie obiektów testowych.
    if created:
        print(f"\nSprzątam {len(created)} obiektów testowych ...")
        try:
            n = tapir.delete_elements(created)
            print(f"  skasowano {n}.")
        except Exception as e:
            print(f"  nie udało się skasować ({e}) — stoją wokół ({BASE_X},{BASE_Y}); "
                  f"możesz je usunąć ręcznie / ac_clean_and_export.py.")

    print("\nGOTOWE. Wklej mi CAŁY wydruk — z niego wybiorę dokładny mechanizm opcji B:")
    print("  • czy Set...A/B zmienia rozmiar (per część),")
    print("  • jakie parametry ma kuchnia (i Twój wybrany blat Casework, jeśli zaznaczony).")


if __name__ == "__main__":
    main()
