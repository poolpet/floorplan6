"""Pydantic schemas for code pack validation.

Schema 1: PackManifest — validates rules/{PACK}/pack.yaml
Schema 2: PackConstants — validates rules/{PACK}/constants.yaml

These are the contract every code pack must satisfy. Validation happens
at load time in `rules._loader.load_pack()`.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PackReference(BaseModel):
    """A legal/regulatory reference cited by the pack."""
    id: str
    title: str
    url: Optional[str] = None


class PackFiles(BaseModel):
    """Filenames inside the pack directory."""
    rules: str = "wt_rules.json"
    constants: str = "constants.yaml"
    user_overrides: str = "user_rules.json"


class PackManifest(BaseModel):
    """Schema for pack.yaml.

    Every code pack must declare its identity, locale, version compatibility,
    and the files it provides.
    """
    code_pack_id: str = Field(..., description="ISO country code or custom id, e.g. 'PL'")
    country_code: str
    locale: str = Field(..., description="POSIX locale like 'pl_PL'")
    version: str = Field(..., description="Pack version, e.g. '1.0'")
    version_compat: str = Field(..., description="FloorPlan6 version range, e.g. '>=0.4.0'")
    display_name: str
    display_name_en: Optional[str] = None
    description: str
    references: List[PackReference] = Field(default_factory=list)
    files: PackFiles = Field(default_factory=PackFiles)


class WTAreaConstants(BaseModel):
    """WT min/max area constants (m²)."""
    bathroom_m2: float
    wc_m2: float


class SetbackDefaults(BaseModel):
    """Default setbacks (m) used when MPZP doesn't specify."""
    front_m: float
    side_m: float
    rear_m: float
    well_to_boundary_m: float


class BuildingClassThresholds(BaseModel):
    """Building height class thresholds (m) per WT."""
    N_max_height_m: float
    SW_max_height_m: float
    W_max_height_m: float
    WW_above_m: float


class PackConstants(BaseModel):
    """Schema for constants.yaml.

    All rule-driven constants extracted from config.py. Adding a new constant
    requires updating this schema (single source of truth).
    """
    # WT area limits
    wt_min_area: Dict[str, float]
    wt_max_area: Dict[str, float]
    wt_min_width: Dict[str, float]

    # Setbacks
    setback_defaults: SetbackDefaults

    # Hub
    hub_min_percent: Dict[str, float]
    hub_max_percent: float
    hub_min_area: Dict[str, float]

    # Apartment types + areas
    apartment_min_area: Dict[str, float]
    apartment_opt_area: Dict[str, float]
    apartment_max_aspect: float
    apartment_mix_default: Dict[str, float]

    # Building class
    building_class: BuildingClassThresholds

    # Corridors + escape
    wt_corridor_internal_min: float
    wt_corridor_public_min: float
    wt_dojscie_max_1klatka: float
    wt_dojscie_max_2klatki: float
    door_min_width: float

    # Stairs
    wt_stair_bieg_width: float
    wt_stair_spocznik_width: float
    wt_stair_step_height_max: float
    wt_stair_blondel: float
    wt_stair_step_width_min: float
    wt_stair_gap_biegs: float

    # Elevator
    wt_elevator_height_threshold: float
    wt_elevator_shaft_w: float
    wt_elevator_shaft_l: float
    wt_elevator_fire_w: float
    wt_elevator_fire_l: float
    wt_elevator_wall_gap: float

    # Wall thicknesses
    wall_thickness_structural: float
    wall_thickness_partition: float
    wall_thickness_bathroom: float

    # Proportions
    proportion_optimal: float
    proportion_max: float
    proportion_absolute_max: float

    # Orientation
    orientation_quality: Dict[str, float]

    # Scorer
    default_scorer_weights: Dict[str, float]

    # Floor reserve
    floor_reserve_ratio: float

    # Parking
    parking_ratio_per_unit: float

    # Usable area correction factor (accounts for wall thicknesses, shafts)
    usable_area_factor: float

    # Mode B (Stage 1 subdivision)
    min_subplot_front_m: float

    # Przedsionek depth per building class
    wt_przedsionek_depth: Dict[str, float]
