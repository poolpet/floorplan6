"""
Diagnostic script — read current selection from ArchiCAD via Tapir.

Run: PYTHONPATH=. python notebooks/test_tapir_selection.py

Prints:
  - raw Tapir GetSelectedElements response
  - GUIDs of selected elements
  - GetDetailsOfElements for each (type, geometry)

If selection is empty even though you have walls/zone/slab selected in AC,
this script will show whether the issue is on AC side (nothing selected)
or in our parser.
"""
from __future__ import annotations

import json

from bridge.tapir_connection import TapirConnection


def main():
    print("Connecting to ArchiCAD via Tapir...")
    tapir = TapirConnection()
    try:
        tapir.connect()
        print("  ✓ Connected")
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return

    print("\n--- GetSelectedElements raw response ---")
    try:
        raw = tapir._execute_tapir("GetSelectedElements", {})
        print(json.dumps(raw, indent=2, default=str))
    except Exception as e:
        print(f"  Error: {e}")
        return

    selected = tapir.get_selected_elements()
    print(f"\n--- Parsed: {len(selected)} elements ---")
    if not selected:
        print("  Empty. AC has nothing selected per Tapir.")
        print("\n  Possible causes:")
        print("    1. AC truly has nothing selected — try Edit → Select All Walls")
        print("    2. Selection is in different storey than current")
        print("    3. Tapir Add-On version returns different keys")
        return

    guids = []
    for elem in selected:
        if isinstance(elem, dict):
            eid = elem.get("elementId", elem)
            guid = eid.get("guid") if isinstance(eid, dict) else str(eid)
        else:
            guid = str(elem)
        guids.append(guid)
        print(f"  GUID: {guid}")

    print("\n--- GetDetailsOfElements ---")
    try:
        details = tapir.get_element_details(guids)
        for d in details:
            etype = d.get("type", "?")
            print(f"  {etype}: {json.dumps({k: v for k, v in d.items() if k != 'details'}, default=str)[:200]}")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
