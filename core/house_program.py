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
    # Open-plan (faza 1): strefa dzienna (DZIENNA) ma ŁĄCZNY cap = min(pct·usable, max).
    # To SUFIT anty-bloat (nie target): wiąże głównie przez `max` na dużych obrysach
    # (ARCHON day-zone ~43 @120 m²); pct=0.50 luźny, by nie klipować normalnych domów,
    # gdzie udział day-zone naturalnie ~0.40-0.47 (rośnie na małych obrysach).
    day_zone_cap_pct: float = 0.60
    day_zone_cap_max: float = 45.0

    def day_zone_cap(self, usable_area_m2: float) -> float:
        """Łączny cap strefy dziennej (salon+kuchnia+jadalnia jako jedna otwarta przestrzeń)."""
        return min(self.day_zone_cap_pct * usable_area_m2, self.day_zone_cap_max)

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
    # capy NETTO ugruntowane na medianach 22+ wzorców (S31b D4): garaz 34 (ref-med 32.7,
    # cap 22 był < ref-min 21.5), master 17.0 (geoMed 17.76), kotlownia 9 (ref-max 12.6),
    # schody 6.0 (ref-med 5.6, winder/dog-leg footprint).
    "salon": 35.0, "kuchnia": 13.0, "sypialnia": 13.0, "master": 17.0,
    "gabinet": 14.0, "pokoj": 14.0, "garaz": 34.0, "kotlownia": 9.0, "pralnia": 6.0,
    "spizarnia": 5.0, "garderoba": 6.0, "wiatrolap": 8.0, "wc": 3.0,
    "schowek": 3.5, "pom": 6.0, "gosp": 6.0, "schody": 6.0,
    # uwaga: "hub" (hol/podest) celowo BEZ cap-u — jest elastycznym sinkiem nadmiaru
    # (na parterze nadmiar bierze salon, na piętrze podest). Twardy cap zawieszałby F1.
}


def default_house_config(storey: str = "parter", master_id: str | None = None) -> HouseProgramConfig:
    """Domyślny program domu (cap-y ARCHON, łazienka ≤5 dla parter/single / ≤8 dla poddasze).

    storey: "parter" | "poddasze" | "single" (parterowiec). cap_for mapuje każde
    ≠"poddasze" na bathroom_parter_max, więc "single" daje łazienkę ≤5 bez dodatkowej logiki.
    """
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

    # Open-plan (faza 1): strefa dzienna (DZIENNA) ma ŁĄCZNY cap. Per-pokój cap-y
    # zostają jako pod-sufity, ale suma salon+kuchnia(+jadalnia) ≤ day_cap. Jeśli
    # %-targety przekraczają łączny cap — ściśnij grupę DZIENNA powyżej min.
    day_ids = [s.id for s in specs if s.strefa == Strefa.DZIENNA]
    day_cap = config.day_zone_cap(usable_area_m2)
    if day_ids:
        day_sum = sum(targets[k] for k in day_ids)
        if day_sum > day_cap + 1e-9:
            excess = day_sum - day_cap
            slack = {k: targets[k] - mins[k] for k in day_ids if targets[k] - mins[k] > 1e-9}
            total_slack = sum(slack.values())
            if total_slack > 1e-9:
                red = min(excess, total_slack)
                for k, sl in slack.items():
                    targets[k] -= red * (sl / total_slack)

    leftover = usable_area_m2 - sum(targets.values())

    if leftover > 1e-9:
        # ARCHON: nadmiar (F1) idzie do STREFY DZIENNEJ do ŁĄCZNEGO cap-u, a RESZTĘ
        # wchłania HUB (elastyczny hol/podest). Sypialnie i usługowe NIE puchną.
        hub_id = next((s.id for s in specs if s.strefa == Strefa.KOMUNIKACJA and s.id == "hub"), None)
        if hub_id is None:
            hub_id = next((s.id for s in specs if s.strefa == Strefa.KOMUNIKACJA), None)
        for _ in range(200):  # 1) wypełnij strefę dzienną do ŁĄCZNEGO cap-u (grupa, nie per-pokój)
            group_room = day_cap - sum(targets[k] for k in day_ids)
            if group_room <= 1e-9 or leftover <= 1e-9:
                break
            headroom = {k: caps[k] - targets[k] for k in day_ids
                        if not math.isinf(caps[k]) and caps[k] - targets[k] > 1e-9}
            total_head = sum(headroom.values())
            if total_head <= 1e-9:
                break
            add = min(leftover, group_room, total_head)
            for k, h in headroom.items():
                targets[k] += add * (h / total_head)
            leftover = usable_area_m2 - sum(targets.values())
        if leftover > 1e-9:
            # 2a) NOCNA water-fill DO CAPÓW (S29, korpus: nadmiar→pokoje, ale najpierw
            # z poszanowaniem capów — master nie pompuje się, póki inne mają headroom;
            # na parterze absorbuje gabinet).
            night_ids = [s.id for s in specs if s.strefa == Strefa.NOCNA]
            for _ in range(200):
                if leftover <= 1e-9:
                    break
                headroom = {k: caps[k] - targets[k] for k in night_ids
                            if not math.isinf(caps[k]) and caps[k] - targets[k] > 1e-9}
                total_head = sum(headroom.values())
                if total_head <= 1e-9:
                    break
                add = min(leftover, total_head)
                for k, h in headroom.items():
                    targets[k] += add * (h / total_head)
                leftover = usable_area_m2 - sum(targets.values())
        if leftover > 1e-9:
            # 2b) RESZTĘ do SYPIALNI (ponad capy — reguła Dawida: korytarz minimalny,
            # nadmiar zyskują pokoje nocne; dzień trzyma ŁĄCZNY cap póki nocne istnieją)
            # lub STREFY DZIENNEJ (parter bez pokoi nocnych) — NIGDY do huba.
            if night_ids:
                sink_pool = night_ids
            elif day_ids:
                sink_pool = day_ids                      # dzień wchłania (soft ponad łączny cap)
            else:
                sink_pool = [k for k in targets if k != hub_id] or list(targets)
            total = sum(targets[k] for k in sink_pool) or 1.0
            for k in sink_pool:
                targets[k] += leftover * (targets[k] / total)
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
