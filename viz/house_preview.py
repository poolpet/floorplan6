"""Stage 4 — orkiestracja podglądu domu jednorodzinnego (GUI-free).

Składa gotowe klocki: generate_house (core, woła worker w UI) → place_furniture
(core) → render_two_storey (viz). Trzymane osobno od ui/main_window.py, żeby
logikę dało się testować bez PyQt — testy GUI padają headless (docs/STATE.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from bridge.room_names import room_name_en
from core.furniture import place_furniture
from core.house_layout import TwoStoreyLayout
from viz.plan_renderer import render_two_storey


def furnish_layout(layout: TwoStoreyLayout, with_furniture: bool) -> tuple[list, list]:
    """(parter_furniture, pietro_furniture). Puste listy gdy with_furniture=False.

    Przekazuje layout.boundary → meble są window-aware (phase 4). Bez tego cała
    świadomość okien byłaby pominięta w realnym produkcie (regresja #18).
    """
    if not with_furniture:
        return [], []
    b = getattr(layout, "boundary", None)
    # Knee-wall v2 (S29): meble WYSOKIE poddasza omijają strefy niskiej ścianki
    # kolankowej (łóżko/WC/wanna mogą stać pod skosem).
    strips = getattr(layout, "attic_low_strips", None) or []
    return (place_furniture(layout.parter_rooms, b),
            place_furniture(layout.pietro_rooms, b, low_zones=strips))


def house_details_text(layout: TwoStoreyLayout) -> str:
    """Opis tekstowy domu po ANGIELSKU: obie kondygnacje + pokoje/powierzchnie (panel UI)."""
    area = getattr(getattr(layout, "boundary", None), "area", None)
    if area is None:
        area = sum(r.area for r in layout.parter_rooms)
    strips = getattr(layout, "attic_low_strips", None) or []
    lines = ["Two-storey single-family house", f"Outline/storey: {area:.1f} m²"]
    if strips:  # knee-wall v2: pełny footprint + strefy niskiej ścianki kolankowej
        low = sum(s.area for s in strips)
        lines.append(f"Attic: knee-wall low zones {low:.1f} m² "
                     f"(along the longer edges)")
    for storey_title, rooms in (("GROUND FLOOR", layout.parter_rooms),
                                ("ATTIC" if strips else "FIRST FLOOR",
                                 layout.pietro_rooms)):
        lines.append("")
        lines.append(f"{storey_title}:")
        for r in rooms:
            lines.append(f"  {room_name_en(r.spec.nazwa):28s} {r.area:5.1f} m²")
    return "\n".join(lines)


def render_house_figure(layout: TwoStoreyLayout, with_furniture: bool, title: Optional[str] = None,
                        save_path: Optional[Path] = None, show: bool = False,
                        architectural: bool = False):
    """Renderuj gotowy TwoStoreyLayout jako 2-panelowy rzut (parter | poddasze)."""
    parter_furniture, pietro_furniture = furnish_layout(layout, with_furniture)
    return render_two_storey(
        layout,
        parter_furniture=parter_furniture,
        pietro_furniture=pietro_furniture,
        title=title,
        save_path=save_path,
        show=show,
        architectural=architectural,
    )
