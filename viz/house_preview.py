"""Stage 4 — orkiestracja podglądu domu jednorodzinnego (GUI-free).

Składa gotowe klocki: generate_house (core, woła worker w UI) → place_furniture
(core) → render_two_storey (viz). Trzymane osobno od ui/main_window.py, żeby
logikę dało się testować bez PyQt — testy GUI padają headless (docs/STATE.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.furniture import place_furniture
from core.house_layout import TwoStoreyLayout
from viz.plan_renderer import render_two_storey


def furnish_layout(layout: TwoStoreyLayout, with_furniture: bool) -> tuple[list, list]:
    """(parter_furniture, pietro_furniture). Puste listy gdy with_furniture=False."""
    if not with_furniture:
        return [], []
    return place_furniture(layout.parter_rooms), place_furniture(layout.pietro_rooms)


def house_details_text(layout: TwoStoreyLayout) -> str:
    """Opis tekstowy domu: obie kondygnacje + pokoje/powierzchnie (panel UI)."""
    area = getattr(getattr(layout, "boundary", None), "area", None)
    if area is None:
        area = sum(r.area for r in layout.parter_rooms)
    lines = ["Dom jednorodzinny 2-kondygnacyjny", f"Obrys/kondygnacja: {area:.1f} m²"]
    for storey_title, rooms in (("PARTER", layout.parter_rooms),
                                ("PIĘTRO", layout.pietro_rooms)):
        lines.append("")
        lines.append(f"{storey_title}:")
        for r in rooms:
            lines.append(f"  {r.spec.nazwa:28s} {r.area:5.1f} m²")
    return "\n".join(lines)


def render_house_figure(layout: TwoStoreyLayout, with_furniture: bool, title: Optional[str] = None,
                        save_path: Optional[Path] = None, show: bool = False):
    """Renderuj gotowy TwoStoreyLayout jako 2-panelowy rzut (PARTER | PIĘTRO)."""
    parter_furniture, pietro_furniture = furnish_layout(layout, with_furniture)
    return render_two_storey(
        layout,
        parter_furniture=parter_furniture,
        pietro_furniture=pietro_furniture,
        title=title,
        save_path=save_path,
        show=show,
    )
