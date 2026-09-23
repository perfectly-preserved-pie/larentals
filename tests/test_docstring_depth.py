"""Keep production Python function documentation useful beyond a summary line."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = ("api", "functions", "pages", "pipelines", "scripts")


def test_production_functions_do_not_have_single_line_docstrings() -> None:
    """Flag thin docstrings as new production code is added.

    A summary can say what a function does while hiding its edge cases or
    reason for existing. The fuller writing standard lives in AGENTS.md.

    Returns:
        None.
    """
    thin: list[str] = []
    for directory in SOURCE_PATHS:
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node)
                if docstring and len(docstring.splitlines()) == 1:
                    thin.append(f"{path.relative_to(ROOT)}:{node.lineno} ({node.name})")

    assert not thin, "Single-line production docstrings:\n" + "\n".join(thin)


# Keep this ceiling at zero; lower it only if a legacy baseline is introduced.
MAX_SUMMARY_ONLY_DOCSTRINGS = 0
SECTION_HEADERS = {"Args:", "Parameters:", "Returns:", "Yields:", "Raises:", "Side Effects:"}


def test_summary_only_production_docstrings_do_not_increase() -> None:
    """Keep new functions from adding to the legacy summary-only backlog.

    A second sentence must add useful context, as described in AGENTS.md.
    The count is a ceiling for existing code, not a writing target.

    Returns:
        None.
    """
    summary_only = 0
    for directory in SOURCE_PATHS:
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                docstring = ast.get_docstring(node)
                if not docstring:
                    continue
                prose: list[str] = []
                for line in docstring.splitlines():
                    if line.strip() in SECTION_HEADERS:
                        break
                    if line.strip():
                        prose.append(line.strip())
                if len(prose) == 1:
                    summary_only += 1

    assert summary_only <= MAX_SUMMARY_ONLY_DOCSTRINGS, (
        f"Summary-only production docstrings grew from "
        f"{MAX_SUMMARY_ONLY_DOCSTRINGS} to {summary_only}"
    )


# This count covers JSDoc immediately preceding JavaScript function forms. Existing inline type
# annotations are not function descriptions.
MAX_SUMMARY_ONLY_JS_DOCS = 0
JSDOC_COMMENT = re.compile(r"/\*\*([\s\S]*?)\*/")
FUNCTION_AFTER_COMMENT = re.compile(
    r"\s*(?:async\s+)?function\b|"
    r"\s*(?:[\w.$]+\s*=\s*)?(?:async\s+)?function\b|"
    r"\s*(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?(?:"
    r"\([^)]*\)|[\w$]+)\s*=>|"
    r"\s*(?:async\s+)?[\w$]+\s*\([^)]*\)\s*\{"
)


def test_summary_only_js_function_docs_do_not_increase() -> None:
    """Keep new JavaScript function JSDoc from enlarging the thin-comment backlog.

    Type tags do not explain the reason for behavior. The count covers
    declarations, function expressions, arrow functions, and methods.

    Returns:
        None.
    """
    summary_only = 0
    for path in (ROOT / "assets" / "js").rglob("*.js"):
        source = path.read_text()
        for match in JSDOC_COMMENT.finditer(source):
            following = source[match.end() : match.end() + 500]
            if not FUNCTION_AFTER_COMMENT.match(following):
                continue
            lines = [
                re.sub(r"^\s*\*\s?", "", line).strip()
                for line in match.group(1).splitlines()
            ]
            prose = [line for line in lines if line and not line.startswith("@")]
            if len(prose) == 1:
                summary_only += 1

    assert summary_only <= MAX_SUMMARY_ONLY_JS_DOCS, (
        f"Summary-only JS function docs grew from "
        f"{MAX_SUMMARY_ONLY_JS_DOCS} to {summary_only}"
    )
