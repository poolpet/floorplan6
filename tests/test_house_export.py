"""`bridge/house_export.export_house_storeys` — wspólna logika obu kondygnacji.

Bez AC i bez Qt: tapir = atrapa (get_stories/activate_story), writer = szpieg.
"""
import pytest


class _Tapir:
    def __init__(self, first=0, last=1, switch_ok=None):
        self.first, self.last = first, last
        self.switch_ok = switch_ok or (lambda i: True)
        self.switched = []
    def get_stories(self): return {"actStory": 0, "firstStory": self.first, "lastStory": self.last}
    def activate_story(self, i): self.switched.append(i); return self.switch_ok(i)


def _layout(two=True):
    return type("L", (), {"pietro_rooms": [object()] if two else []})()


def _wire(monkeypatch, per_storey=None):
    import bridge.house_export as he
    calls = []
    def fake(layout, storey="parter", tapir=None, offset=(0, 0), include_furniture=False):
        calls.append(storey)
        return {"zones": ["z"] * 2, "walls": ["w"], "doors": [], "windows": [], "labels": ["l"]}
    monkeypatch.setattr(he, "export_house_to_archicad", per_storey or fake)
    return calls


def test_both_storeys_ground_floor_index_zero(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    t = _Tapir(first=-1, last=1)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], t)
    assert t.switched == [0, 1] and calls == ["parter", "poddasze"]
    assert r["inserted"] == ["parter", "poddasze"] and r["partial"] is False and r["error"] is None
    assert r["totals"] == {"zones": 4, "walls": 2, "doors": 0, "windows": 0, "labels": 2}


def test_no_storey_above_ground_blocks_before_write(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], _Tapir(first=0, last=0))
    assert calls == [] and r["inserted"] == [] and "no storey above" in r["error"]


def test_switch_failure_midway_is_partial(monkeypatch):
    from bridge.house_export import export_house_storeys
    calls = _wire(monkeypatch)
    t = _Tapir(switch_ok=lambda i: i == 0)
    r = export_house_storeys(_layout(), ["parter", "poddasze"], t)
    assert calls == ["parter"] and r["inserted"] == ["parter"] and r["partial"] is True
    assert "already been inserted" in r["error"] and "only the remaining" in r["error"]


def test_single_storey_layout_attic_error(monkeypatch):
    from bridge.house_export import export_house_storeys
    def boom(layout, storey="parter", **kw):
        raise ValueError("A single-storey house has no attic — choose 'parter'.")
    _wire(monkeypatch, per_storey=boom)
    r = export_house_storeys(_layout(two=False), ["poddasze"], _Tapir())
    assert r["error"] and "single-storey" in r["error"] and r["inserted"] == []
