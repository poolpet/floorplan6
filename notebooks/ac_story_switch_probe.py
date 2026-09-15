"""LIVE-RESEARCH: namierz DZIAŁAJĄCY kształt param `ChangeWindow` do przełączania aktywnej story.

Tło: auto-switch (1-klik obie kondygnacje) potrzebuje programowego ustawienia aktywnej
kondygnacji PRZED tworzeniem stref/ścian (active story = piętro które piszemy). Komenda
`ChangeWindow` istnieje, ale `{navigatorItemId:{guid}}` rzuca schema-reject offline
(`additionalProperties #/navigatorItemId`). Ten probe próbuje KILKU kształtów na żywym AC,
sprawdza czy `GetStories.actStory` się zmienił, i PRZYWRACA pierwotną story.

Uruchom przy OTWARTYM, BEZCZYNNYM AC (zamknij dialogi/narzędzia — inaczej 'ongoing user input'):
    PYTHONPATH=. venv/bin/python notebooks/ac_story_switch_probe.py [port]
Wklej cały output — na jego podstawie zbuduję `TapirConnection.activate_story`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archicad import ACConnection

from bridge.tapir_connection import TAPIR_NAMESPACE as NS


def tap(conn, name, params=None):
    cid = conn.types.AddOnCommandId(NS, name)
    return conn.commands.ExecuteAddOnCommand(cid, params or {}) or {}


def story_navitems(conn, first=0):
    """ProjectMap → StoryItems (top-down) → reversed = idx rosnące. Zwraca {idx: guid}.

    Klucze w PRZESTRZENI INDEKSÓW AC (`first` = `GetStories.firstStory`) — ta sama
    konwencja co `TapirConnection.story_navitems`: przy piwnicy first = -1.
    """
    acc, act = conn.commands, conn.types
    tid = act.NavigatorTreeId(type="ProjectMap")
    tree = acc.GetNavigatorItemTree(tid)
    guids_top_down = []

    def walk(node):
        nid = getattr(getattr(node, "navigatorItemId", None), "guid", None)
        ntype = getattr(node, "type", None)
        if ntype == "StoryItem" and nid:
            guids_top_down.append(str(nid))
        for ch in (getattr(node, "children", None) or []):
            walk(getattr(ch, "navigatorItem", ch))

    walk(getattr(tree, "rootItem", tree))
    return {first + i: g for i, g in enumerate(reversed(guids_top_down))}


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19723
    conn = ACConnection.connect(port=port)
    if conn is None:
        print(f"Brak AC na porcie {port}."); return

    st = tap(conn, "GetStories")
    act0, first, last = st.get("actStory"), st.get("firstStory"), st.get("lastStory")
    print(f"PORT {port}: actStory={act0} first={first} last={last} "
          f"stories={[s.get('name') for s in st.get('stories', [])]}")
    if act0 is None or last == first:
        print("Brak ≥2 kondygnacji do testu przełączenia."); return

    idx2guid = story_navitems(conn, int(first if first is not None else 0))
    print(f"idx→navigatorItemId: {idx2guid}")
    target = next(i for i in idx2guid if isinstance(i, int) and i != act0)
    g = idx2guid[target]
    print(f"\nPróba przełączenia actStory {act0} → {target} (guid {g}):")

    # Kandydaci na kształt param ChangeWindow — pierwszy który zmieni actStory WYGRYWA.
    shapes = [
        ("navigatorItemId:{guid}", {"navigatorItemId": {"guid": g}}),
        ("navigatorItemId:{guid,type}", {"navigatorItemId": {"guid": g, "type": "StoryItem"}}),
        ("{guid} (płaski)", {"guid": g}),
        ("databaseId+FloorPlan", {"databaseId": {"guid": g}, "windowType": "FloorPlan"}),
        ("windowType FloorPlan (bez targetu)", {"windowType": "FloorPlan"}),
    ]
    winner = None
    for label, params in shapes:
        try:
            tap(conn, "ChangeWindow", params)
            now = tap(conn, "GetStories").get("actStory")
            ok = (now == target)
            print(f"   [{'OK ' if ok else 'nie'}] {label:34s} → actStory={now}")
            if ok and winner is None:
                winner = (label, params)
        except Exception as e:
            print(f"   [err] {label:34s} → {e!r}"[:160])

    # PRZYWRÓĆ pierwotną story (najlepszym znanym kształtem).
    back = idx2guid.get(act0)
    if winner and back:
        _, wparams = winner
        restore = dict(wparams)
        try:
            if "navigatorItemId" in restore:
                restore = {"navigatorItemId": dict(restore["navigatorItemId"], guid=back)}
            elif "guid" in restore:
                restore = dict(restore, guid=back)
            tap(conn, "ChangeWindow", restore)
        except Exception as e:
            print(f"   [err] przywrócenie story {act0} nie poszło: {e!r}"[:160])
    elif winner:
        print(f"   [uwaga] brak nav-itemu dla story {act0} — nie przywracam automatycznie.")
    print(f"\nactStory po przywróceniu: {tap(conn, 'GetStories').get('actStory')} (oczekiwane {act0})")
    print(f"\nZWYCIĘZCA: {winner[0] if winner else 'BRAK — żaden kształt nie przełączył (zgłoś, spróbujemy floorIndex retarget)'}")


if __name__ == "__main__":
    main()
