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

    @pytest.mark.xfail(reason="constants.yaml not yet created — Week 2 Task 9")
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
