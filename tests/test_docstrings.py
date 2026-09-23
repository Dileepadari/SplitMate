"""Every public definition in the package carries a docstring.

This is checked rather than asked for, because documentation coverage is exactly
the kind of thing that is complete on the day it is written and 80 per cent six
months later. `docs/COMMENT_STYLE.md` says what belongs in one.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "splitmate"
SOURCES = sorted(PACKAGE.rglob("*.py"))


def _public_definitions(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ) and not node.name.startswith("_"):
            yield node


def test_the_package_was_found():
    """A typo in the path would make every other test here pass by finding nothing."""
    assert SOURCES, f"no sources under {PACKAGE}"
    assert len(SOURCES) >= 15


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_module_has_a_docstring(path):
    assert ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))), (
        f"{path.relative_to(PACKAGE.parent)} has no module docstring"
    )


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_public_definition_has_a_docstring(path):
    undocumented = [
        f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}"
        for node in _public_definitions(path)
        if not ast.get_docstring(node)
    ]
    assert not undocumented, "missing docstrings:\n  " + "\n  ".join(undocumented)
