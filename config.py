"""FloorPlan6 — Python-runtime constants (NOT rule-driven).

Rule-driven constants (WT_*, HUB_*, APARTMENT_*, etc.) live in
`rules/{PACK_ID}/constants.yaml` and are loaded via `rules._loader.load_pack`.

This module retains ONLY constants that are tied to the Python implementation
itself (precision scale, sentinel values), not to any architectural code.
"""
from __future__ import annotations

# CP-SAT solver works in centimeters (integer). Multiply meters by SCALE.
SCALE = 100  # cm per m
