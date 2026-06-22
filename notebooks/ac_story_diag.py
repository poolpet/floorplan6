"""Diagnostyka kondygnacji/instancji AC — GDZIE wylądowały strefy/ściany eksportu.

Cel: rozstrzygnąć "poddasze nie wchodzi do AC". Skanuje WSZYSTKIE instancje AC
(porty 19723..19730), w każdej listuje strefy + ściany Z numerem (DOM-PARTER /
DOM-PODDASZE) i pozycją Z (story czytamy z zCoordinate — Tapir NIE zwraca floorInd
w detalach strefy).

WAŻNE (lekcje z 2026-06-19):
- Tapir `GetElementsByType` potrafi zwrócić 0 mimo że elementy istnieją → GUID-y
  bierzemy ze STANDARDOWEGO API: GetAllElements + GetTypesOfElements, sięgając
  `t.typeOfElement.elementType` / `.elementId.guid` (NIE `t.elementType`!).
- Properties (name/numberStr/zCoordinate) czytamy Tapirowym GetDetailsOfElements
  (działa na podanych GUID-ach nawet gdy listing nie działa).

Uruchom (przy otwartym AC + Tapir), NAJLEPIEJ od razu po eksporcie, PRZED undo:
    venv/bin/python notebooks/ac_story_diag.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archicad import ACConnection

NS = "TapirCommand"
PORTS = range(19723, 19731)


def _tap(conn, name, params=None):
    """Dowolna komenda Tapir AddOn → dict ({'_err': ...} przy błędzie)."""
    try:
        cid = conn.types.AddOnCommandId(NS, name)
        return conn.commands.ExecuteAddOnCommand(cid, params or {}) or {}
    except Exception as e:
        return {"_err": repr(e)}


def _details(conn, guids):
    """Tapir GetDetailsOfElements na liście GUID-ów → lista detali."""
    if not guids:
        return []
    cid = conn.types.AddOnCommandId(NS, "GetDetailsOfElements")
    elems = [{"elementId": {"guid": g}} for g in guids]
    res = conn.commands.ExecuteAddOnCommand(cid, {"elements": elems}) or {}
    return res.get("detailsOfElements", res.get("elements", []))


def inventory(port):
    try:
        conn = ACConnection.connect(port=port)
    except Exception:
        return
    if conn is None:
        return

    # Nazwa dokumentu + aktywna kondygnacja — drukuj NAJPIERW (widoczne nawet gdy AC zajęty).
    proj = _tap(conn, "GetProjectInfo").get("projectName", "?")
    st = _tap(conn, "GetStories")
    act = st.get("actStory", "?")
    story_names = [s.get("name", "") for s in st.get("stories", [])] if isinstance(st, dict) else []
    print(f"\n{'=' * 66}\nPORT {port}  proj={proj!r}  actStory={act}  stories={story_names}\n{'=' * 66}")

    try:
        all_ids = conn.commands.GetAllElements()
        types = conn.commands.GetTypesOfElements(all_ids)
    except Exception as e:
        print(f"   GetAllElements BŁĄD {e!r} (AC zajęty? domknij dialog/narzędzie i powtórz)")
        return

    zg, wg = [], []
    for t in types:
        toe = getattr(t, "typeOfElement", None)
        if toe is None:
            continue
        et = getattr(toe, "elementType", None)
        eid = getattr(toe, "elementId", None)
        guid = getattr(eid, "guid", None) if eid is not None else None
        if not guid:
            continue
        if et == "Zone":
            zg.append(str(guid))
        elif et == "Wall":
            wg.append(str(guid))

    print(f"   Zone={len(zg)}  Wall={len(wg)}")

    zd = _details(conn, zg)
    dom_rows, by = [], Counter()
    for d in zd:
        inner = d.get("details", d) if isinstance(d, dict) else {}
        name = inner.get("name", "?")
        number = str(inner.get("numberStr", inner.get("number", "?")))
        z = inner.get("zCoordinate", "?")
        if number.startswith("DOM-"):          # nasze eksporty
            dom_rows.append((name, number, z))
        prefix = number.rsplit("-", 1)[0] if "-" in number else number
        by[(prefix, z)] += 1

    if dom_rows:
        print(f">>> NASZE strefy DOM-* na porcie {port} (proj {proj!r}, actStory={act}): {len(dom_rows)}")
        for name, number, z in dom_rows:
            print(f"    {name:24s} | {number:24s} | z={z}")
    else:
        print(">>> NASZYCH stref DOM-* tu NIE MA")
    print("Wszystkie strefy (prefix × zCoordinate):")
    for (prefix, z), n in sorted(by.items(), key=lambda kv: str(kv[0])):
        print(f"    {str(prefix):22s} @ z={z}: {n}")

    wd = _details(conn, wg)
    wby = Counter(
        (d.get("details", d) if isinstance(d, dict) else {}).get("zCoordinate", "?")
        for d in wd
    )
    print("Ściany per zCoordinate:", dict(wby))


def main():
    print("Skan instancji AC na portach 19723..19730 ...")
    for p in PORTS:
        inventory(p)
    print("\nGOTOWE — wklej cały output Claude'owi (najlepiej od razu po eksporcie).")


if __name__ == "__main__":
    main()
