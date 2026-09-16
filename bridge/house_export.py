"""Wstawianie domu (parter + poddasze) do Archicada — JEDNO źródło prawdy.

Ten sam przebieg woła GUI (`ui/main_window._export_house_to_archicad`) i serwis
(`service/app._export`): plan kondygnacji z `parter_story_index`, przełączanie
story w AC, zapis przez `bridge.house_writer` i sumowanie wyniku. Bez Qt —
moduł leci też z wątku serwisu, więc nie wolno tu importować PyQt.

Wynik jest CZYSTYM dictem (bez wyjątków dla przewidzianych blokad), żeby GUI
zbudowało z niego dialog, a serwis — kod HTTP:

    {"inserted": [str], "totals": {...}, "partial": bool,
     "error": str | None, "error_stage": str | None}

`error_stage`: "storey_missing" (brak kondygnacji nad parterem, nic nie
wstawiono), "storey_switch" (AC nie dał się przełączyć), "write" (writer
odrzucił kondygnację, np. poddasze w parterowcu).
"""
from __future__ import annotations

import logging

from bridge.tapir_connection import parter_story_index

logger = logging.getLogger(__name__)

# Etykiety dla komunikatów (GUI ma swoje STOREY_LABELS — te same wartości; tu
# muszą być, bo z modułu korzysta też serwis, który GUI nie widzi).
STOREY_LABELS = {"parter": "Ground floor", "poddasze": "Attic"}
COUNTED = ("zones", "walls", "doors", "windows", "labels")


def export_house_to_archicad(*args, **kwargs):
    """Cienka delegacja do `bridge.house_writer.export_house_to_archicad`.

    Lazy import (writer ciągnie szablony i solver), a przy okazji szew testowy
    działa z obu stron: testy tego modułu podmieniają
    `bridge.house_export.export_house_to_archicad`, testy GUI —
    `bridge.house_writer.export_house_to_archicad`; wołanie przez tę nazwę
    honoruje obie podmiany.
    """
    from bridge.house_writer import export_house_to_archicad as _write
    return _write(*args, **kwargs)


def storey_label(storey: str) -> str:
    """Angielska etykieta kondygnacji dla komunikatów ('parter' → 'Ground floor')."""
    return STOREY_LABELS.get(storey, storey)


def export_house_storeys(layout, storeys: list[str], tapir, *,
                         include_furniture: bool = False,
                         offset: tuple[float, float] = (0.0, 0.0),
                         switch: bool = True) -> dict:
    """Wstaw wskazane kondygnacje domu do AC; zwróć raport (bez rzucania wyjątków).

    `storeys`: kolejność wstawiania, np. ["parter", "poddasze"]. `switch=True`
    (serwis, GUI w trybie "obie") przełącza aktywną story AC przed każdym
    zapisem; `switch=False` (GUI, jedna kondygnacja) pisze na kondygnację, którą
    user ustawił sam — wtedy guard i override zostają po stronie GUI.
    """
    totals = {k: 0 for k in COUNTED}
    inserted: list[str] = []
    report = {"inserted": inserted, "totals": totals, "partial": False,
              "error": None, "error_stage": None}
    targets: dict[str, int] = {}

    if switch:
        st = tapir.get_stories() or {}
        first = int(st.get("firstStory", 0))
        last = int(st.get("lastStory", 0))
        # Parter to indeks 0 w przestrzeni AC (gdy istnieje) — NIE `firstStory`:
        # przy piwnicy firstStory = -1 i parter leży o jeden wyżej. Ta sama
        # reguła co w `check_active_story` (jedno źródło prawdy).
        parter_idx = parter_story_index(first, last)
        poddasze_idx = parter_idx + 1
        targets = {"parter": parter_idx, "poddasze": poddasze_idx}
        # Brak kondygnacji nad parterem: blokuj PRZED jakimkolwiek zapisem —
        # inaczej parter wszedłby, poddasze nie, a ponowna próba zdublowałaby parter.
        if "poddasze" in storeys and poddasze_idx > last:
            report["error"] = (
                f"The Archicad project has no storey above the ground floor "
                f"(index {poddasze_idx}) — add a storey in Archicad or insert "
                f"only the ground floor."
            )
            report["error_stage"] = "storey_missing"
            return report

    for storey in storeys:
        if switch:
            # Nieznany klucz kondygnacji nie ma indeksu — nie przełączamy, odmowę
            # (z sensownym komunikatem) wystawi writer niżej.
            target = targets.get(storey)
            if target is not None and not tapir.activate_story(target):
                report["error"] = _switch_error(target, storey, inserted)
                report["error_stage"] = "storey_switch"
                logger.warning("eksport domu: brak przełączenia na story %s (%s)",
                               target, storey)
                break
        try:
            written = export_house_to_archicad(
                layout, storey=storey, tapir=tapir, offset=offset,
                include_furniture=include_furniture,
            )
        except ValueError as e:
            # Przewidziana odmowa writera (np. poddasze w parterowcu) — to nie
            # jest awaria: raportujemy tekstem, wstawione kondygnacje zostają.
            report["error"] = str(e)
            report["error_stage"] = "write"
            logger.warning("eksport domu: writer odrzucił '%s' (%s)", storey, e)
            break
        for k in totals:
            totals[k] += len(written.get(k) or [])
        inserted.append(storey)

    report["partial"] = bool(inserted) and len(inserted) < len(storeys)
    return report


def _switch_error(target, storey: str, inserted: list[str]) -> str:
    """Komunikat o nieudanym przełączeniu story — inny, gdy część już jest w AC."""
    label = storey_label(storey)
    head = f"Could not switch Archicad to storey {target} ('{label}')."
    if inserted:
        # Część już w AC — user MUSI wstawić tylko resztę, inaczej dubel.
        done = ", ".join(storey_label(s) for s in inserted)
        return (f"{head} {done} has already been inserted; switch the storey "
                f"manually in Archicad and insert only the remaining storey.")
    return (f"{head} Switch the storey manually in Archicad and insert each "
            f"storey separately.")
