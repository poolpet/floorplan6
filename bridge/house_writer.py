"""Eksport domu (TwoStoreyLayout) do ArchiCAD — JEDNA kondygnacja na raz (2-pass).

Reuse writera mieszkań: buduje per-kondygnację FloorPlan z właściwym szablonem
(house_single_storey / house_parter / house_pietro) i woła export_plan_to_archicad.
Tapir tworzy na AKTYWNEJ kondygnacji AC — user przełącza kondygnację między przebiegami.
Meble domyślnie WYŁĄCZONE (Tapir nie obraca obiektów — zamrożone).
"""
from __future__ import annotations

from typing import Optional

from core.models import FloorPlan
from bridge.plan_writer import export_plan_to_archicad
from bridge.tapir_connection import TapirConnection


def export_house_to_archicad(
    layout,
    storey: str = "parter",
    tapir: Optional[TapirConnection] = None,
    offset: tuple[float, float] = (0.0, 0.0),
    include_furniture: bool = False,
) -> dict:
    """Wstaw JEDNĄ kondygnację domu do AC (na aktywną kondygnację AC).

    layout: TwoStoreyLayout. storey: "parter" | "poddasze". Parterowiec (brak
    pietro_rooms) → tylko "parter" (szablon house_single_storey).
    Zwraca dict z export_plan_to_archicad + klucz "storey".
    Reuse wyboru szablonu z core.plan_contract.house_to_contract.
    """
    from core.template_selector import load_all_templates  # lazy — jak w house_to_contract
    tpls = {t.id: t for t in load_all_templates()}
    single = not layout.pietro_rooms

    if storey == "parter":
        rooms = layout.parter_rooms
        boundary = layout.boundary
        template = tpls.get("house_single_storey") if single else tpls.get("house_parter")
    elif storey == "poddasze":
        if single:
            raise ValueError("Parterowiec nie ma poddasza — wybierz 'parter'.")
        rooms = layout.pietro_rooms
        boundary = getattr(layout, "attic_boundary", None) or layout.boundary
        template = tpls.get("house_pietro")
    else:
        raise ValueError(f"Nieznana kondygnacja: {storey!r} (parter|poddasze)")

    plan = FloorPlan(boundary=boundary, template=template, rooms=rooms)
    # apartment_id JAWNIE — szablon domu nie ma typ_mieszkania (export_plan_to_archicad:95).
    result = export_plan_to_archicad(
        plan,
        tapir=tapir,
        offset=offset,
        include_furniture=include_furniture,
        apartment_id=f"DOM-{storey.upper()}",
    )
    result["storey"] = storey
    return result
