"""Regression coverage for repository-wide function documentation standards."""

import ast
from pathlib import Path
import re
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_all_python_functions_are_typed_and_documented() -> None:
    """Require complete type hints and applicable docstring sections.

    Honor Git's ignore rules so local environments and generated copies do not
    affect the check. Include untracked source so new files are checked before
    they are staged.

    Returns:
        None.
    """
    issues: list[str] = []

    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=PROJECT_ROOT,
    ).decode()
    for relative_path in sorted(set(files.split("\0")) - {""}):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            location = f"{relative_path}:{node.lineno} ({node.name})"
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
