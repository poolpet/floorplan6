import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_namespace_constant_is_floorforge():
    from bridge.tapir_connection import TAPIR_NAMESPACE
    assert TAPIR_NAMESPACE == "FloorForgeCommand"


def test_no_namespace_literal_outside_bridge():
    """Literał przestrzeni komend istnieje tylko w bridge/tapir_connection.py."""
    hits = []
    for p in list(ROOT.glob("*.py")) + list(ROOT.glob("ui/*.py")) + list(ROOT.glob("service/*.py")) \
            + list(ROOT.glob("notebooks/*.py")) + list(ROOT.glob("bridge/*.py")):
        if p.name.endswith(" 2.py"):
            continue
        if p == ROOT / "bridge" / "tapir_connection.py":
            continue
        if re.search(r'"(TapirCommand|FloorForgeCommand)"', p.read_text(encoding="utf-8")):
            hits.append(str(p.relative_to(ROOT)))
    assert hits == [], f"literał przestrzeni komend poza bridge: {hits}"


def test_addon_namespace_matches_python():
    src = (ROOT / "addon" / "Sources" / "CommandBase.cpp").read_text(encoding="utf-8")
    from bridge.tapir_connection import TAPIR_NAMESPACE
    assert f'CommandNamespace = "{TAPIR_NAMESPACE}"' in src
