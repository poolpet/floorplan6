"""CZYTNIK + DIFF ZAZNACZENIA (uruchamia Claude): zrzuca dla każdego zaznaczonego obiektu
nazwę + wymiary, a potem DIFFUJE parametry GDL między zaznaczonymi — pokazuje TYLKO te,
które się RÓŻNIĄ. Dzięki temu od razu widać, który parametr odpowiada za wyposażenie
szafki (zlew / płyta / nic), bez przeglądania 60 parametrów.

    PYTHONPATH=. venv/bin/python notebooks/ac_read_selection.py
"""
from __future__ import annotations


def _guid(e):
    eid = e.get("elementId", e) if isinstance(e, dict) else e
    return eid.get("guid") if isinstance(eid, dict) else str(eid)


def _params(tapir, guid):
    try:
        res = tapir._execute_tapir("GetGDLParametersOfElements",
                                   {"elements": [{"elementId": {"guid": guid}}]})
    except Exception as e:  # noqa: BLE001
        return {}, repr(e)
    lst = res.get("gdlParametersOfElements", [])
    entry = lst[0] if lst else {}
    plist = entry.get("parameters", []) if isinstance(entry, dict) else (entry if isinstance(entry, list) else [])
    return {p.get("name"): p for p in plist if isinstance(p, dict)}, None


def main():
    from bridge.tapir_connection import TapirConnection
    tapir = TapirConnection()
    tapir.connect()
    print(f"Połączono port {tapir.active_port}")

    guids = [g for g in (_guid(e) for e in tapir.get_selected_elements()) if g]
    if not guids:
        print("BRAK ZAZNACZENIA — zaznacz szafki i powtórz.")
        return
    print(f"Zaznaczono {len(guids)} elem.\n")

    objs = []  # (name, dims, params)
    for i, g in enumerate(guids):
        det = tapir.get_element_details([g])
        inner = (det[0].get("details", det[0]) if det and isinstance(det[0], dict) else {})
        lib = inner.get("libPart", {})
        name = lib.get("name") if isinstance(lib, dict) else "?"
        dims = inner.get("dimensions")
        params, err = _params(tapir, g)
        objs.append((name, dims, params))
        print(f"[{i}] '{name}'  dims={dims}  ({len(params)} paramów)" + (f"  GDLerr={err}" if err else ""))

    # DIFF: parametry (nie-tablice), których wartość różni się między zaznaczonymi.
    print("\n=== PARAMETRY KTÓRE SIĘ RÓŻNIĄ między zaznaczonymi (= wyposażenie/warianty) ===")
    all_names = set()
    for _, _, p in objs:
        all_names |= set(p.keys())
    any_diff = False
    for pname in sorted(all_names):
        cells = [p.get(pname) for _, _, p in objs]
        vals = [c.get("value") if isinstance(c, dict) else None for c in cells]
        if any(isinstance(v, list) for v in vals):
            continue  # pomiń tablice (refLinePoints itp.)
        if len({str(v) for v in vals}) <= 1:
            continue  # identyczne → pomiń
        any_diff = True
        first = next((c for c in cells if isinstance(c, dict)), {})
        typ = first.get("type", "?")
        disp = first.get("displayName", "")
        print(f"  {pname:22s} [{typ}] ({disp})")
        for i, v in enumerate(vals):
            print(f"      [{i}] = {v}")
    if not any_diff:
        print("  (żadne nie-tablicowe parametry się nie różnią — może to różne obiekty biblioteczne?)")


if __name__ == "__main__":
    main()
