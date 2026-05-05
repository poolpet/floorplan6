"""
Wybór szablonu topologicznego — Krok 2 algorytmu outside-in.

Wczytuje szablony z templates/*.json i wybiera najlepszy dla danego
typu mieszkania i obrysu.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.models import (
    Boundary, Template, RoomSpec, AdjacencyRule,
    Strefa, Orientation,
)


# ============================================================
# Ładowanie szablonów z JSON
# ============================================================

_STREFA_MAP = {
    "DZIENNA": Strefa.DZIENNA,
    "NOCNA": Strefa.NOCNA,
    "USŁUGOWA": Strefa.USLUGOWA,
    "KOMUNIKACJA": Strefa.KOMUNIKACJA,
}


def _load_template_from_json(path: Path) -> Template:
    """Wczytaj szablon z pliku JSON."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    pokoje = []
    for r in raw["pokoje"]:
        spec = RoomSpec(
            id=r["id"],
            nazwa=r["nazwa"],
            strefa=_STREFA_MAP[r["strefa"]],
            wymaga_okna=r["wymaga_okna"],
            priorytet_fasady=r.get("priorytet_fasady"),
            preferowana_orientacja=[
                Orientation(o) for o in r.get("preferowana_orientacja", [])
            ],
            min_powierzchnia=r.get("min_powierzchnia", 0),
            opt_powierzchnia=r.get("opt_powierzchnia", 0),
            min_szerokosc=r.get("min_szerokosc", 0),
            max_proporcja=r.get("max_proporcja", 2.0),
            procent_powierzchni=tuple(r.get("procent_powierzchni", (0, 1))),
        )
        pokoje.append(spec)

    sasiedztwo = []
    for e in raw["sasiedztwo"]:
        sasiedztwo.append(AdjacencyRule(
            room_a=e["room_a"],
            room_b=e["room_b"],
            connection_type=e.get("connection_type", "door"),
        ))

    return Template(
        id=raw["id"],
        nazwa=raw["nazwa"],
        typ_mieszkania=raw["typ_mieszkania"],
        pokoje=pokoje,
        sasiedztwo=sasiedztwo,
        source=raw.get("source", "manual"),
        confidence=raw.get("confidence", 1.0),
        n_source_plans=raw.get("n_source_plans", 0),
    )


def load_all_templates(templates_dir: Optional[Path] = None) -> list[Template]:
    """Wczytaj wszystkie szablony z katalogu templates/."""
    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"
    templates = []
    for fp in sorted(templates_dir.glob("*.json")):
        templates.append(_load_template_from_json(fp))
    return templates


# ============================================================
# Selekcja szablonu
# ============================================================

def select_templates(
    mtype: str,
    boundary: Boundary,
    all_templates: Optional[list[Template]] = None,
) -> list[Template]:
    """Wybierz pasujące szablony dla danego typu mieszkania i obrysu.

    Zwraca listę szablonów posortowanych wg dopasowania (najlepszy pierwszy).
    """
    if all_templates is None:
        all_templates = load_all_templates()

    # Filtruj po typie mieszkania
    candidates = [t for t in all_templates if t.typ_mieszkania == mtype]

    if not candidates:
        raise ValueError(
            f"Brak szablonów dla typu {mtype}. "
            f"Dostępne: {sorted(set(t.typ_mieszkania for t in all_templates))}"
        )

    # Sprawdź czy pokoje z oknami zmieszczą się na fasadach
    scored = []
    for template in candidates:
        score = _score_template_fit(template, boundary)
        scored.append((score, template))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


def _score_template_fit(template: Template, boundary: Boundary) -> float:
    """Ocena dopasowania szablonu do obrysu.

    Wyższy score = lepsze dopasowanie.
    """
    score = 0.0

    # Ile pokoi wymaga okna (fasady)?
    window_rooms = [p for p in template.pokoje if p.wymaga_okna]
    n_facade_edges = len(boundary.facade_edges)

    # Czy wystarczy fasad?
    total_facade_length = sum(e.length for e in boundary.facade_edges)
    min_window_width = sum(p.min_szerokosc for p in window_rooms)

    if total_facade_length >= min_window_width:
        score += 10.0  # fasady wystarczą
    else:
        score -= 5.0  # za mało fasad

    # Preferuj szablony z większą liczbą source plans (lepiej potwierdzone)
    score += template.n_source_plans * 0.5

    # Preferuj szablony z mniejszą liczbą pokoi przy małych obrysach
    area = boundary.area
    n_rooms = len(template.pokoje)
    min_total = sum(p.min_powierzchnia for p in template.pokoje)

    if area >= min_total * 1.1:
        score += 5.0  # wystarczy miejsca
    elif area >= min_total:
        score += 2.0  # ciasno ale się zmieści
    else:
        score -= 10.0  # za mały obrys

    return score


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    from shapely.geometry import Polygon

    templates = load_all_templates()
    print(f"Wczytano {len(templates)} szablonów:")
    for t in templates:
        rooms_str = ", ".join(p.id for p in t.pokoje)
        print(f"  {t.id} ({t.typ_mieszkania}): {rooms_str}")

    # Test selekcji dla M2, boundary 8×6m
    poly = Polygon([(0, 0), (8, 0), (8, 6), (0, 6)])
    from core.boundary_analyzer import analyze_boundary
    boundary = analyze_boundary(poly, (4.0, 0.0))

    print(f"\nSelekcja dla M2, boundary {boundary.width}×{boundary.height}m:")
    selected = select_templates("M2", boundary, templates)
    for t in selected:
        print(f"  → {t.id}")
