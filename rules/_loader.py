"""Code pack loader.

Loads a code pack from `rules/{PACK_ID}/` with manifest + rules + constants
+ user overrides. Validates against Pydantic schemas (`rules._schema`).

Usage:
    from rules._loader import load_pack
    pack = load_pack("PL")
    bathroom_max = pack.constants["wt_max_area"]["bathroom_m2"]  # 5.0
    rule_001 = next(r for r in pack.rules["reguly"] if r["id"] == "wt_001")
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from rules._schema import PackConstants, PackManifest

RULES_ROOT = Path(__file__).resolve().parent


class CodePackError(Exception):
    """Raised when a code pack is missing or invalid."""


@dataclass
class CodePack:
    """A loaded, validated code pack.

    Attributes:
        pack_id: e.g. "PL"
        locale: e.g. "pl_PL"
        version: pack version, e.g. "1.0"
        manifest: parsed PackManifest (Pydantic model)
        rules: parsed wt_rules.json content (dict with "reguly" list)
        constants: parsed constants.yaml content (dict)
        user_overrides: parsed user_rules.json content (dict)
        path: filesystem path to the pack directory
    """
    pack_id: str
    locale: str
    version: str
    manifest: PackManifest
    rules: Dict[str, Any] = field(default_factory=dict)
    constants: Dict[str, Any] = field(default_factory=dict)
    user_overrides: Dict[str, Any] = field(default_factory=dict)
    path: Path = field(default_factory=Path)


def load_pack(pack_id: str = "PL") -> CodePack:
    """Load and validate a code pack.

    Args:
        pack_id: Pack directory name under `rules/`. Defaults to "PL".

    Returns:
        CodePack with manifest, rules, constants, user_overrides parsed.

    Raises:
        CodePackError: if pack directory is missing, manifest invalid,
            or constants fail schema validation.
    """
    pack_dir = RULES_ROOT / pack_id
    if not pack_dir.is_dir():
        raise CodePackError(
            f"Code pack '{pack_id}' not found at {pack_dir}. "
            f"Available packs: {[p.name for p in RULES_ROOT.iterdir() if p.is_dir() and not p.name.startswith('_')]}"
        )

    manifest_path = pack_dir / "pack.yaml"
    if not manifest_path.is_file():
        raise CodePackError(f"Missing pack.yaml in {pack_dir}")

    try:
        manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = PackManifest(**manifest_data)
    except (yaml.YAMLError, ValidationError) as exc:
        raise CodePackError(f"Invalid pack.yaml in {pack_dir}: {exc}") from exc

    rules_path = pack_dir / manifest.files.rules
    if not rules_path.is_file():
        raise CodePackError(f"Missing rules file: {rules_path}")
    rules = json.loads(rules_path.read_text(encoding="utf-8"))

    constants_path = pack_dir / manifest.files.constants
    constants: Dict[str, Any] = {}
    if constants_path.is_file():
        constants_data = yaml.safe_load(constants_path.read_text(encoding="utf-8"))
        try:
            PackConstants(**constants_data)  # validate
        except ValidationError as exc:
            raise CodePackError(f"Invalid constants.yaml in {pack_dir}: {exc}") from exc
        constants = constants_data

    user_overrides_path = pack_dir / manifest.files.user_overrides
    user_overrides: Dict[str, Any] = {}
    if user_overrides_path.is_file():
        user_overrides = json.loads(user_overrides_path.read_text(encoding="utf-8"))

    return CodePack(
        pack_id=manifest.code_pack_id,
        locale=manifest.locale,
        version=manifest.version,
        manifest=manifest,
        rules=rules,
        constants=constants,
        user_overrides=user_overrides,
        path=pack_dir,
    )
