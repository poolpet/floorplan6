"""Tests for rules._loader.load_pack()."""
from __future__ import annotations

import pytest

from rules._loader import CodePack, CodePackError, load_pack


class TestLoadPackHappyPath:
    def test_load_pl_pack_returns_codepack(self):
        pack = load_pack("PL")
        assert isinstance(pack, CodePack)
        assert pack.pack_id == "PL"
        assert pack.locale == "pl_PL"
        assert pack.version == "1.0"

    def test_pl_pack_has_rules_dict(self):
        pack = load_pack("PL")
        assert isinstance(pack.rules, dict)
        assert "reguly" in pack.rules
        # 19 WT rules expected
        assert len(pack.rules["reguly"]) == 19

    def test_pl_pack_has_constants(self):
        pack = load_pack("PL")
        assert isinstance(pack.constants, dict)
        assert "wt_max_area" in pack.constants
        assert pack.constants["wt_max_area"]["bathroom_m2"] == 5.0

    def test_pl_pack_has_user_overrides(self):
        pack = load_pack("PL")
        # user_rules.json has empty "reguly" list by default
        assert isinstance(pack.user_overrides, dict)


class TestLoadPackErrors:
    def test_unknown_pack_raises(self):
        with pytest.raises(CodePackError, match="not found"):
            load_pack("NONEXISTENT")

    def test_default_pack_is_pl(self):
        pack = load_pack()  # no arg
        assert pack.pack_id == "PL"


class TestLoadPackEdgeCases:
    def test_missing_manifest_raises(self, tmp_path, monkeypatch):
        # Create a pack dir with no pack.yaml
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Missing pack.yaml"):
            load_pack("BAD")

    def test_invalid_manifest_raises(self, tmp_path, monkeypatch):
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        # Manifest missing required fields
        (bad_pack / "pack.yaml").write_text("code_pack_id: BAD\n")
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Invalid pack.yaml"):
            load_pack("BAD")

    def test_missing_rules_file_raises(self, tmp_path, monkeypatch):
        bad_pack = tmp_path / "BAD"
        bad_pack.mkdir()
        (bad_pack / "pack.yaml").write_text("""
code_pack_id: BAD
country_code: BAD
locale: xx_XX
version: "1.0"
version_compat: ">=0.0.0"
display_name: "Bad pack"
description: "Bad"
""")
        monkeypatch.setattr("rules._loader.RULES_ROOT", tmp_path)
        with pytest.raises(CodePackError, match="Missing rules file"):
            load_pack("BAD")

    def test_pack_path_attribute_set(self):
        pack = load_pack("PL")
        assert pack.path.name == "PL"
        assert (pack.path / "pack.yaml").is_file()


class TestDefaultPack:
    def test_default_pack_is_memoized(self):
        from rules._loader import get_default_pack, reset_default_pack
        reset_default_pack()
        p1 = get_default_pack()
        p2 = get_default_pack()
        assert p1 is p2  # same instance

    def test_set_default_pack_overrides(self):
        from rules._loader import get_default_pack, set_default_pack, reset_default_pack
        reset_default_pack()
        original = get_default_pack()
        set_default_pack(original)
        assert get_default_pack() is original
        reset_default_pack()
