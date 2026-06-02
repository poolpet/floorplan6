"""Konfigurowalny program domu jednorodzinnego — cap-y metraży + %-udziały.

Zastępuje regułę Q6 ("salon zjada 80% nadmiaru") na ścieżce DOMU rozkładem
opartym na ARCHON: każdy pokój dostaje target = clamp(%-udział·usable, min, cap),
a żaden pokój mieszkalny nie puchnie ponad swój cap. Resztę do F1 (==) wchłaniają
pokoje elastyczne/overflow, NIE salon (patrz solver).

Cap-y i %-udziały są EDYTOWALNE (config przekazywany per-run; domyślne z ARCHON,
Session 17). Ścieżka mieszkań M1-M5 tego modułu nie używa — pozostaje na Q6.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.models import RoomSpec, Strefa


@dataclass
class HouseProgramConfig:
    """Edytowalny program domu: cap-y per typ pokoju + %-udziały.

    caps: klucz = prefiks id pokoju (np. "salon", "sypialnia"), wartość = max m².
    pct_overrides: nadpisanie procent_powierzchni z szablonu (UI/per-run).
    """
    caps: dict[str, float] = field(default_factory=dict)
    bathroom_parter_max: float = 5.0
    bathroom_poddasze_max: float = 8.0
    storey: str = "parter"  # "parter" | "poddasze" — steruje cap-em łazienki
    master_id: str | None = None  # id pokoju traktowanego jak master (cap "master")
    pct_overrides: dict[str, tuple[float, float]] = field(default_factory=dict)

    def cap_for(self, spec: RoomSpec) -> float:
        key = spec.id.split("_")[0]
        if key == "lazienka":  # F2 różnicowane per kondygnacja
            return self.bathroom_poddasze_max if self.storey == "poddasze" else self.bathroom_parter_max
        if self.master_id is not None and spec.id == self.master_id:
            return self.caps.get("master", self.caps.get(key, float("inf")))
        return self.caps.get(key, float("inf"))

    def pct_for(self, spec: RoomSpec) -> tuple[float, float]:
        key = spec.id.split("_")[0]
        return self.pct_overrides.get(key, spec.procent_powierzchni)


# Domyślne cap-y metraży [m²] ugruntowane na korpusie ARCHON (Session 17).
# EDYTOWALNE — UI/per-run nadpisuje przez HouseProgramConfig.caps.
DEFAULT_HOUSE_CAPS: dict[str, float] = {
    "salon": 35.0, "kuchnia": 13.0, "sypialnia": 13.0, "master": 16.5,
    "gabinet": 14.0, "pokoj": 14.0, "kotlownia": 8.0, "pralnia": 6.0,
    "spizarnia": 5.0, "garderoba": 6.0, "wiatrolap": 8.0, "wc": 3.0,
    "schowek": 3.5, "pom": 6.0, "gosp": 6.0, "schody": 5.0,
    # uwaga: "hub" (hol/podest) celowo BEZ cap-u — jest elastycznym sinkiem nadmiaru
    # (na parterze nadmiar bierze salon, na piętrze podest). Twardy cap zawieszałby F1.
}


def default_house_config(storey: str = "parter", master_id: str | None = None) -> HouseProgramConfig:
    """Domyślny program domu (cap-y ARCHON, łazienka parter ≤5 / poddasze ≤8)."""
    return HouseProgramConfig(
        caps=dict(DEFAULT_HOUSE_CAPS),
        bathroom_parter_max=5.0,
        bathroom_poddasze_max=8.0,
        storey=storey,
        master_id=master_id,
    )


def compute_house_targets(
    specs: list[RoomSpec], usable_area_m2: float, config: HouseProgramConfig
) -> dict[str, float]:
    """Target powierzchni per pokój: clamp(%-udział·usable, min, cap), a resztę
    do F1 (Σ == usable) rozkłada water-fillingiem po headroomie (cap−target).

    Salon NIGDY nie przekracza cap-u (reszta idzie do innych pokoi z zapasem;
    gdy wszystkie cap-y nasycone — nadwyżka zostaje i sygnalizuje potrzebę
    pokoi overflow, którą obsługuje generator domu, nie ta funkcja).
    """
    targets: dict[str, float] = {}
    caps: dict[str, float] = {}
    mins: dict[str, float] = {}
    for s in specs:
        lo, hi = config.pct_for(s)
        mid = (lo + hi) / 2.0
        cap = config.cap_for(s)
        targets[s.id] = max(s.min_powierzchnia, min(mid * usable_area_m2, cap))
        caps[s.id] = cap
        mins[s.id] = s.min_powierzchnia

    leftover = usable_area_m2 - sum(targets.values())

    if leftover > 1e-9:
        # ARCHON: nadmiar (F1) idzie do STREFY DZIENNEJ (salon/kuchnia) do cap-ów,
        # a RESZTĘ wchłania HUB (elastyczny hol/podest). Sypialnie i usługowe NIE
        # puchną — zostają na %-targecie ≤ cap. (Stara wersja rozlewała nadmiar po
        # wszystkich headroomach, więc przeciekał w sypialnie — bloat na małym holu.)
        hub_id = next((s.id for s in specs if s.strefa == Strefa.KOMUNIKACJA and s.id == "hub"), None)
        if hub_id is None:
            hub_id = next((s.id for s in specs if s.strefa == Strefa.KOMUNIKACJA), None)
        day_ids = [s.id for s in specs if s.strefa == Strefa.DZIENNA]
        for _ in range(200):  # 1) wypełnij strefę dzienną do cap-ów
            headroom = {k: caps[k] - targets[k] for k in day_ids
                        if not math.isinf(caps[k]) and caps[k] - targets[k] > 1e-9}
            if not headroom or leftover <= 1e-9:
                break
            total_head = sum(headroom.values())
            add = min(leftover, total_head)
            for k, h in headroom.items():
                targets[k] += add * (h / total_head)
            leftover = usable_area_m2 - sum(targets.values())
        if leftover > 1e-9:  # 2) resztę do huba (elastyczny sink); brak huba → największy pokój
            sink_id = hub_id if hub_id is not None else max(targets, key=lambda k: targets[k])
            targets[sink_id] += leftover
            leftover = usable_area_m2 - sum(targets.values())
    elif leftover < -1e-9:  # mały obrys: ściśnij pokoje powyżej min ku min
        for _ in range(200):
            slack = {k: targets[k] - mins[k] for k in targets if targets[k] - mins[k] > 1e-9}
            need = sum(targets.values()) - usable_area_m2
            if not slack or need <= 1e-9:
                break
            total_slack = sum(slack.values())
            sub = min(need, total_slack)
            for k, sl in slack.items():
                targets[k] -= sub * (sl / total_slack)

    return targets


def unabsorbed_leftover(
    specs: list[RoomSpec], usable_area_m2: float, config: HouseProgramConfig
) -> float:
    """Ile m² zostaje po nasyceniu wszystkich cap-ów (>0 => dodaj pokój overflow)."""
    return round(usable_area_m2 - sum(compute_house_targets(specs, usable_area_m2, config).values()), 6)
