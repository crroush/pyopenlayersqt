#!/usr/bin/env python3
"""Ensure Python 3.8-safe deferred evaluation for modern annotations.

Python 3.8 can parse annotations such as ``list[str]`` and ``int | None``,
but evaluating them at import time can fail unless the module opts into
``from __future__ import annotations``.  This script audits annotations without
importing project modules, so it can run in CI before dependencies are present.
"""

import ast
from pathlib import Path

BUILTIN_GENERIC_NAMES = {"dict", "frozenset", "list", "set", "tuple", "type"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "pyopenlayersqt"
FUTURE_IMPORT = "from __future__ import annotations"


def _has_future_annotations(source):
    return FUTURE_IMPORT in source


def _annotation_requires_future(annotation):
    for node in ast.walk(annotation):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return True
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in BUILTIN_GENERIC_NAMES
        ):
            return True
    return False


def _iter_annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.returns is not None:
                yield node.returns


def _module_requires_future(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return any(_annotation_requires_future(annotation) for annotation in _iter_annotations(tree))


def main():
    missing = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if _module_requires_future(path) and not _has_future_annotations(source):
            missing.append(path.relative_to(PROJECT_ROOT))

    if missing:
        print(
            "Modules using PEP 604 unions or built-in generic annotations must "
            "import 'from __future__ import annotations' for Python 3.8:"
        )
        for path in missing:
            print("- {0}".format(path))
        raise SystemExit(1)

    print(
        "All modules using PEP 604 unions or built-in generic annotations "
        "defer annotation evaluation."
    )


if __name__ == "__main__":
    main()
