"""Bramka §9: żaden string widoczny dla testera nie jest po polsku.

Beta idzie do testerów spoza Polski (spec `2026-09-15-floorforge-bundle-design.md` §9),
więc GUI, komunikaty błędów, podgląd i payload lecący do Archicada muszą być po
angielsku. Pojedyncze asercje w innych plikach łapią tylko te teksty, które akurat
ktoś przetestował — ta bramka skanuje AST i łapie każdy nowy literał.

Zakres celowo WĄSKI: tylko moduły, których stringi wychodzą do użytkownika.
`core/` jest zamrożone (polskie `RoomSpec.nazwa` to też identyfikatory solvera) —
tłumaczy je `bridge/room_names.py` na szwach (eksport/podgląd), patrz
`tests/test_room_names.py`.

Poza skanem (świadomie):
- docstringi i komentarze — nie trafiają do okna,
- argumenty `logger.*` / `logging.*` / `print()` — log techniczny może być mieszany (§9),
- `bridge/room_names.py` — to JEST słownik polskich nazw,
- klucze kontraktu `parter` / `poddasze` / `piętro` (whitelist), bo jadą do solvera
  i `bridge/house_writer`, a nie na ekran.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCANNED = [
    "ui/main_window.py",
    "ui/ac_status_widget.py",
    "ui/user_errors.py",
    "service/errors.py",
    "service/app.py",
    "service/solve_adapter.py",
    "service/client.py",
    "service/jobs.py",
    "service/results.py",
    "bridge/plan_writer.py",
    "bridge/house_writer.py",
    "bridge/boundary_reader.py",
    "bridge/tapir_connection.py",
    "viz/plan_renderer.py",
    "viz/house_preview.py",
    "floorforge_app.py",
]

POLISH = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")

# Klucze kontraktu — NIE etykiety. Dopasowanie dokładne (case-sensitive).
WHITELIST = {"parter", "poddasze", "piętro"}

LOGGER_OWNERS = {"logger", "logging", "log", "_log", "LOGGER"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id() węzłów będących docstringiem modułu/funkcji/klasy."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant) \
                    and isinstance(node.body[0].value.value, str):
                out.add(id(node.body[0].value))
    return out


def _is_logging_call(node: ast.Call) -> bool:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id == "print"
    if isinstance(fn, ast.Attribute):
        owner = fn.value
        if isinstance(owner, ast.Name):
            return owner.id in LOGGER_OWNERS
        if isinstance(owner, ast.Attribute):
            return owner.attr in LOGGER_OWNERS
    return False


def _logging_arg_nodes(tree: ast.AST) -> set[int]:
    """id() każdego węzła siedzącego w argumentach wywołania logującego."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_logging_call(node):
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                for sub in ast.walk(arg):
                    out.add(id(sub))
    return out


def _polish_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    skip = _docstring_nodes(tree) | _logging_arg_nodes(tree)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip or node.value in WHITELIST:
            continue
        if POLISH.search(node.value):
            hits.append((node.lineno, node.value))
    return hits


@pytest.mark.parametrize("rel", SCANNED)
def test_no_polish_letters_in_user_strings(rel):
    path = ROOT / rel
    assert path.exists(), rel
    hits = _polish_literals(path)
    assert not hits, "\n".join(f"{rel}:{ln}: {txt!r}" for ln, txt in hits)


def test_guard_actually_detects_polish(tmp_path):
    """Sam skaner musi łapać — inaczej bramka jest zielona z powodu błędu w bramce."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""Docstring po polsku — pomijany: ściana."""\n'
        'import logging\n'
        'logger = logging.getLogger(__name__)\n'
        'logger.warning("log po polsku — ściana")\n'
        'print("print po polsku — ściana")\n'
        'KEY = "parter"\n'
        'BAD = "Ściana działowa"\n',
        encoding="utf-8",
    )
    hits = _polish_literals(sample)
    assert [h[1] for h in hits] == ["Ściana działowa"]
