"""Regression coverage for repository-wide function documentation standards."""

import ast
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".git", ".venv", "venv"}


def test_all_python_functions_are_typed_and_documented() -> None:
    """Require complete type hints and applicable docstring sections.

    Returns:
        None.
    """
    issues: list[str] = []

    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            continue

        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            location = f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} ({node.name})"
            docstring = ast.get_docstring(node) or ""
            parameters = [
                parameter
                for parameter in (
                    node.args.posonlyargs
                    + node.args.args
                    + node.args.kwonlyargs
                )
                if parameter.arg not in {"self", "cls"}
            ]
            if node.args.vararg:
                parameters.append(node.args.vararg)
            if node.args.kwarg:
                parameters.append(node.args.kwarg)

            if not docstring:
                issues.append(f"{location}: missing docstring")
            if node.returns is None:
                issues.append(f"{location}: missing return annotation")

            for parameter in parameters:
                if parameter.annotation is None:
                    issues.append(
                        f"{location}: parameter {parameter.arg!r} lacks a type hint"
                    )
                documented = re.search(
                    rf"(?m)^\s*\**{re.escape(parameter.arg)}"
                    r"(?:\s*\([^\n]*\))?\s*:",
                    docstring,
                )
                if not documented:
                    issues.append(
                        f"{location}: parameter {parameter.arg!r} is undocumented"
                    )
                generic_description = re.search(
                    rf"(?m)^\s*\**{re.escape(parameter.arg)}"
                    r"(?:\s*\([^\n]*\))?\s*:\s*"
                    r"(?:The .+ value\.|.+ consumed by .+\(\)\.)\s*$",
                    docstring,
                )
                if generic_description:
                    issues.append(
                        f"{location}: parameter {parameter.arg!r} has a generic description"
                    )

            if parameters and not re.search(
                r"(?m)^\s*(?:Args|Parameters):\s*$",
                docstring,
            ):
                issues.append(f"{location}: missing Args/Parameters section")
            if not re.search(r"(?m)^\s*(?:Returns|Yields):\s*$", docstring):
                issues.append(f"{location}: missing Returns/Yields section")

    assert not issues, "\n" + "\n".join(issues)
