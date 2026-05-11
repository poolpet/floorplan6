"""
Stage 1 — plot verifier (ported from claude code/archicad-checker/verifier.py
on 2026-05-07 with Q13/Q14/Q17 changes).

Loads WT 2002 rules from rules/PL/wt_rules.json + user MPZP overrides from
rules/PL/user_rules.json via rules._loader.load_pack. Verifies a designed project against:
  1. Indicators WZ/WIZ/PBC (wt_014, wt_015, wt_016)
  2. Wall setbacks from boundaries (wt_001, wt_002, wt_003)
  3. Site element distances — well/septic (wt_004–wt_008)  *** Q13/Q17 gated
  4. Parking count + dimensions (wt_009, wt_010, wt_019)
  5. User-supplied MPZP rules

Q13 (DECIDED 2026-05-07): when MPZPParameters.infrastructure_municipal=True,
skip well/septic checks (city water/sewer assumed).
Q17 (DECIDED 2026-05-07): when housing_type=WIELORODZINNA, skip well/septic
checks unconditionally ("nierealne albo skrajnie niewykonalne").
Q14 (DECIDED 2026-05-07): keep 5% warning band by default; PlotVerifier
takes a `strict` flag (default False) — when True, behaviour matches F10
(no soft tolerance, binary OK/VIOLATION).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.plot_model import HousingType, Plot
from core.plot_indicators import PlotIndicators
from core.site_element_model import SiteElement, SiteElementType
from core.site_wall_model import SiteWall, WallOpeningType
from rules._loader import load_pack

logger = logging.getLogger(__name__)


class VerificationStatus(str, Enum):
    ZGODNY = "ZGODNY"
    NIEZGODNY = "NIEZGODNY"
    OSTRZEZENIE = "OSTRZEZENIE"
    NIEWERYFIKOWANY = "NIEWERYFIKOWANY"


STATUS_ICON = {
    VerificationStatus.ZGODNY: "✅",
    VerificationStatus.NIEZGODNY: "❌",
    VerificationStatus.OSTRZEZENIE: "⚠️",
    VerificationStatus.NIEWERYFIKOWANY: "ℹ️",
}

STATUS_COLOR = {
    VerificationStatus.ZGODNY: "#27AE60",
    VerificationStatus.NIEZGODNY: "#E74C3C",
    VerificationStatus.OSTRZEZENIE: "#F39C12",
    VerificationStatus.NIEWERYFIKOWANY: "#95A5A6",
}

STATUS_ORDER = {
    VerificationStatus.NIEZGODNY: 0,
    VerificationStatus.OSTRZEZENIE: 1,
    VerificationStatus.ZGODNY: 2,
    VerificationStatus.NIEWERYFIKOWANY: 3,
}


@dataclass
class VerificationResult:
    """One verification result for one rule and one plot."""
    rule_id: str
    name: str
    status: VerificationStatus = VerificationStatus.NIEWERYFIKOWANY
    designed_value: Optional[float] = None
    designed_value_str: str = ""
    required_value: Optional[float] = None
    required_value_str: str = ""
    requirement_type: str = "max"   # "min" or "max"
    unit: str = ""
    legal_basis: str = ""
    description: str = ""
    conditional_requirement: str = ""
    plot_number: str = ""

    @property
    def icon(self) -> str:
        return STATUS_ICON.get(self.status, "ℹ️")

    @property
    def color(self) -> str:
        return STATUS_COLOR.get(self.status, "#95A5A6")

    @property
    def exceedance(self) -> Optional[float]:
        """How far the designed value is over/under requirement (negative = within)."""
        if self.designed_value is None or self.required_value is None:
            return None
        if self.requirement_type == "max":
            return self.designed_value - self.required_value
        return self.required_value - self.designed_value

    def __str__(self) -> str:
        op = "≤" if self.requirement_type == "max" else "≥"
        return (
            f"{self.icon} {self.name}: {self.designed_value_str} {op} "
            f"{self.required_value_str} {self.unit} [{self.legal_basis}]"
        )


class PlotVerifier:
    """Plot project verification engine.

    Args:
        strict: when True, the 5% warning band is disabled — every value
                over `max` (or under `min`) is reported as NIEZGODNY (Q14b).
                Default False keeps the band (Q14a).
    """

    def __init__(self, strict: bool = False, pack_id: str = "PL"):
        self.strict = strict
        self._wt_rules: List[Dict] = []
        self._user_rules: List[Dict] = []
        self._load_rules(pack_id)

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def _load_rules(self, pack_id: str = "PL") -> None:
        pack = load_pack(pack_id)
        self._wt_rules = pack.rules.get("reguly", [])
        user_overrides_raw = pack.user_overrides.get("reguly", [])
        self._user_rules = [
            r for r in user_overrides_raw
            if r.get("aktywna", True)
        ]
        logger.info(
            "Loaded rules: %d WT, %d user MPZP.",
            len(self._wt_rules), len(self._user_rules),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        plot: Plot,
        elements: List[SiteElement],
        walls: List[SiteWall],
        indicators: PlotIndicators,
    ) -> List[VerificationResult]:
        """Run all 5 categories of checks and return sorted results."""
        results: List[VerificationResult] = []

        results += self._verify_indicators(plot, indicators)
        if walls:
            results += self._verify_wall_setbacks(plot, walls)
        if self._well_septic_active(plot):
            results += self._verify_element_distances(plot, elements)
        results += self._verify_parking(plot, indicators)
        results += self._verify_user_rules(plot, elements, indicators)

        results.sort(key=lambda r: STATUS_ORDER.get(r.status, 99))
        return results

    def _well_septic_active(self, plot: Plot) -> bool:
        """Q13 + Q17 gating logic for wt_004–wt_008."""
        if plot.housing_type == HousingType.WIELORODZINNA:
            return False  # Q17 — never check well/septic for multi-family
        if plot.mpzp.infrastructure_municipal:
            return False  # Q13 — city water/sewer skips these checks
        return True

    # ------------------------------------------------------------------
    # 1. Indicators (WZ / WIZ / PBC)
    # ------------------------------------------------------------------

    def _verify_indicators(
        self, plot: Plot, indicators: PlotIndicators
    ) -> List[VerificationResult]:
        mpzp = plot.mpzp
        results = []

        results.append(self._check_max(
            rule_id="wt_014",
            name="Wskaźnik zabudowy (WZ)",
            designed=indicators.wz_designed,
            limit=mpzp.max_wz,
            unit="",
            legal_basis="MPZP / § 12 WT",
            plot_number=plot.number,
            format_fn=lambda v: f"{v:.3f} ({v*100:.1f}%)",
        ))

        results.append(self._check_max(
            rule_id="wt_015",
            name="Wskaźnik intensywności zabudowy (WIZ)",
            designed=indicators.wiz_designed,
            limit=mpzp.max_wiz,
            unit="",
            legal_basis="MPZP",
            plot_number=plot.number,
            format_fn=lambda v: f"{v:.3f} ({v*100:.1f}%)",
        ))

        results.append(self._check_min(
            rule_id="wt_016",
            name="Powierzchnia biologicznie czynna (PBC)",
            designed=indicators.pbc_percent,
            limit=mpzp.min_pbc_percent,
            unit="%",
            legal_basis="MPZP",
            plot_number=plot.number,
            format_fn=lambda v: f"{v:.1f}%",
        ))

        return results

    # ------------------------------------------------------------------
    # 2. Wall setbacks
    # ------------------------------------------------------------------

    def _verify_wall_setbacks(
        self, plot: Plot, walls: List[SiteWall]
    ) -> List[VerificationResult]:
        results = []
        for wall in walls:
            if wall.distance_to_boundary is None or not wall.near_boundary:
                continue

            required = wall.required_min_setback
            distance = wall.distance_to_boundary

            if wall.wall_type == WallOpeningType.BEZ_OTWOROW:
                legal_basis = "§ 12 ust. 2 WT"
                wall_label = "bez otworów"
            else:
                legal_basis = "§ 12 ust. 1 pkt 2 WT"
                wall_label = "z otworami"

            r = VerificationResult(
                rule_id=f"sciana_{wall.index}",
                name=f"Odległość ściany {wall_label} ({wall.compass_direction}) od granicy",
                requirement_type="min",
                designed_value=round(distance, 3),
                designed_value_str=f"{distance:.2f} m",
                required_value=required,
                required_value_str=f"{required:.1f} m",
                unit="m",
                legal_basis=legal_basis,
                plot_number=plot.number,
            )

            if distance >= required:
                r.status = VerificationStatus.ZGODNY
            elif (not self.strict) and distance >= required - 0.01:
                r.status = VerificationStatus.OSTRZEZENIE
                r.description = f"Ściana {wall_label} w odległości granicznej."
            else:
                r.status = VerificationStatus.NIEZGODNY
                short = required - distance
                r.description = (
                    f"Ściana {wall_label} zbyt blisko granicy o {short:.2f} m. "
                    f"Wymagane min {required:.1f} m, projektowane {distance:.2f} m."
                )
            results.append(r)
        return results

    # ------------------------------------------------------------------
    # 3. Element distances (well / septic / building) — Q13/Q17 gated
    # ------------------------------------------------------------------

    def _verify_element_distances(
        self, plot: Plot, elements: List[SiteElement]
    ) -> List[VerificationResult]:
        results = []
        well = self._find(elements, SiteElementType.STUDNIA)
        septic = self._find(elements, SiteElementType.SZAMBO)
        building = self._find(elements, SiteElementType.BUDYNEK_GLOWNY)

        if well and well.geometry:
            distance = self._min_distance_to_boundaries(well, plot)
            results.append(self._check_min(
                rule_id="wt_004",
                name="Odległość studni od granicy działki",
                designed=distance,
                limit=5.0,
                unit="m",
                legal_basis="§ 31 ust. 1 WT",
                plot_number=plot.number,
                format_fn=lambda v: f"{v:.2f} m",
            ))

        if septic and septic.geometry:
            distance = self._min_distance_to_boundaries(septic, plot)
            results.append(self._check_min(
                rule_id="wt_006",
                name="Odległość szamba od granicy działki",
                designed=distance,
                limit=5.0,
                unit="m",
                legal_basis="§ 36 ust. 1 WT",
                plot_number=plot.number,
                format_fn=lambda v: f"{v:.2f} m",
            ))

        if well and septic and well.geometry and septic.geometry:
            distance = well.geometry.distance(septic.geometry)
            results.append(self._check_min(
                rule_id="wt_005",
                name="Odległość studni od szamba",
                designed=distance,
                limit=15.0,
                unit="m",
                legal_basis="§ 31 ust. 2 WT",
                plot_number=plot.number,
                format_fn=lambda v: f"{v:.2f} m",
            ))

        if septic and building and septic.geometry and building.geometry:
            distance = septic.geometry.distance(building.geometry)
            results.append(self._check_min(
                rule_id="wt_007",
                name="Odległość szamba od budynku własnego",
                designed=distance,
                limit=10.0,
                unit="m",
                legal_basis="§ 36 ust. 2 pkt a WT",
                plot_number=plot.number,
                format_fn=lambda v: f"{v:.2f} m",
            ))

        return results

    # ------------------------------------------------------------------
    # 4. Parking
    # ------------------------------------------------------------------

    def _verify_parking(
        self, plot: Plot, indicators: PlotIndicators
    ) -> List[VerificationResult]:
        required = indicators.required_parking_spaces
        designed = indicators.designed_parking_spaces

        r = VerificationResult(
            rule_id="mpzp_parkingi",
            name="Miejsca parkingowe",
            requirement_type="min",
            designed_value=float(designed),
            designed_value_str=f"{designed} stanowisk",
            required_value=float(required),
            required_value_str=f"{required} stanowisk",
            unit="szt.",
            legal_basis="MPZP / § 18 WT",
            plot_number=plot.number,
        )
        if designed >= required:
            r.status = VerificationStatus.ZGODNY
        else:
            r.status = VerificationStatus.NIEZGODNY
            short = required - designed
            r.description = (
                f"Brakuje {short} miejsc postojowych. "
                f"Wymagane: {required}, projektowane: {designed}."
            )
        return [r]

    # ------------------------------------------------------------------
    # 5. User MPZP rules (dynamic)
    # ------------------------------------------------------------------

    def _verify_user_rules(
        self,
        plot: Plot,
        elements: List[SiteElement],
        indicators: PlotIndicators,
    ) -> List[VerificationResult]:
        results = []
        param_map = {
            "wz": indicators.wz_designed,
            "wiz": indicators.wiz_designed,
            "pbc": indicators.pbc_percent,
            "wysokosc_zabudowy": max(
                (el.height for el in elements if el.is_building), default=0.0
            ),
            "kondygnacje": indicators.floor_count,
            "linia_zabudowy_od_drogi": plot.mpzp.setback_from_road,
        }

        for rule in self._user_rules:
            param = rule.get("parametr")
            if param not in param_map:
                continue
            value = param_map[param]
            limit = rule.get("wartosc")
            if limit is None:
                continue

            kind = rule.get("typ", "max")
            kwargs = dict(
                rule_id=rule["id"],
                name=rule["nazwa"],
                designed=value,
                limit=limit,
                unit=rule.get("jednostka", ""),
                legal_basis=rule.get("podstawa_prawna", "MPZP"),
                plot_number=plot.number,
                format_fn=lambda v: f"{v:.3f}",
            )
            if kind == "max":
                results.append(self._check_max(**kwargs))
            else:
                results.append(self._check_min(**kwargs))

        return results

    # ------------------------------------------------------------------
    # Generic check helpers — Q14 5% band lives here
    # ------------------------------------------------------------------

    def _check_max(
        self,
        rule_id: str,
        name: str,
        designed: float,
        limit: float,
        unit: str,
        legal_basis: str,
        plot_number: str,
        format_fn: Optional[Callable[[float], str]] = None,
    ) -> VerificationResult:
        fmt = format_fn or (lambda v: f"{v:.3f}")
        # 0.1% absolute tolerance for floating-point equality.
        epsilon = limit * 0.001
        r = VerificationResult(
            rule_id=rule_id,
            name=name,
            requirement_type="max",
            designed_value=designed,
            designed_value_str=fmt(designed),
            required_value=limit,
            required_value_str=fmt(limit),
            unit=unit,
            legal_basis=legal_basis,
            plot_number=plot_number,
        )

        if designed <= limit + epsilon:
            r.status = VerificationStatus.ZGODNY
            return r

        if (not self.strict) and designed <= limit * 1.05:
            r.status = VerificationStatus.OSTRZEZENIE
            over = designed - limit
            r.description = (
                f"Wartość przekracza limit o {fmt(over)} {unit} "
                f"(w paśmie tolerancji 5%)."
            )
            return r

        r.status = VerificationStatus.NIEZGODNY
        over = designed - limit
        r.description = f"Wartość przekracza dopuszczalne maximum o {fmt(over)} {unit}."
        return r

    def _check_min(
        self,
        rule_id: str,
        name: str,
        designed: float,
        limit: float,
        unit: str,
        legal_basis: str,
        plot_number: str,
        format_fn: Optional[Callable[[float], str]] = None,
    ) -> VerificationResult:
        fmt = format_fn or (lambda v: f"{v:.3f}")
        epsilon = limit * 0.001
        r = VerificationResult(
            rule_id=rule_id,
            name=name,
            requirement_type="min",
            designed_value=designed,
            designed_value_str=fmt(designed),
            required_value=limit,
            required_value_str=fmt(limit),
            unit=unit,
            legal_basis=legal_basis,
            plot_number=plot_number,
        )

        if designed >= limit - epsilon:
            r.status = VerificationStatus.ZGODNY
            return r

        if (not self.strict) and designed >= limit * 0.95:
            r.status = VerificationStatus.OSTRZEZENIE
            short = limit - designed
            r.description = (
                f"Wartość poniżej minimum o {fmt(short)} {unit} "
                f"(w paśmie tolerancji 5%)."
            )
            return r

        r.status = VerificationStatus.NIEZGODNY
        short = limit - designed
        r.description = f"Wartość poniżej wymaganego minimum o {fmt(short)} {unit}."
        return r

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _min_distance_to_boundaries(element: SiteElement, plot: Plot) -> float:
        min_d = float("inf")
        for boundary in plot.boundaries:
            try:
                d = element.geometry.distance(boundary.geometry)
                if d < min_d:
                    min_d = d
            except Exception:
                pass
        return min_d if min_d < float("inf") else 0.0

    @staticmethod
    def _find(
        elements: List[SiteElement], element_type: SiteElementType
    ) -> Optional[SiteElement]:
        for el in elements:
            if el.element_type == element_type:
                return el
        return None

    # ------------------------------------------------------------------
    # Conditional warnings (project requirements section in reports)
    # ------------------------------------------------------------------

    def generate_conditional_warnings(
        self, walls: List[SiteWall], plot: Plot
    ) -> List[str]:
        """Build the 'Warunki do spełnienia w projekcie wykonawczym' list."""
        warnings = []
        for wall in walls:
            if (
                wall.wall_type == WallOpeningType.BEZ_OTWOROW
                and wall.distance_to_boundary is not None
                and wall.distance_to_boundary < 3.0
            ):
                warnings.append(
                    f"⚠️ WARUNEK PROJEKTU: ściana {wall.compass_direction} "
                    f"(Ściana {wall.index + 1}) musi być zaprojektowana BEZ otworów "
                    f"okiennych i drzwiowych — zbliżenie do "
                    f"{wall.distance_to_boundary:.2f} m od granicy "
                    f"({wall.boundary_type_label or 'sąsiedniej'})."
                )
        return warnings
