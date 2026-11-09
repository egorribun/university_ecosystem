#!/usr/bin/env python3
"""Offline census of test blocks that perform no result check (AUD-428).

Python test modules (``tests/**/test_*.py`` and ``*_test.py``) are parsed with
``ast``. A test block is a ``test_*`` function or method. Go test files
(``services/**/*_test.go`` and ``gen/**/*_test.go``) are read with a small
brace-aware scanner that blanks strings and comments before any matching, so a
string or comment cannot satisfy the census. A ``t.Run`` body is a block of its
own. The census never runs a test and never imports the go toolchain.

Exit status: 0 when every resultless block is listed in the reviewed allowlist
and every allowlist entry still matches a resultless block; 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST = REPOSITORY_ROOT / "quality" / "test-block-census-allowlist.json"
SCHEMA_VERSION = 1
PYTHON_ROOT = "tests"
GO_ROOTS: tuple[str, ...] = ("services", "gen")
HELPER_PREFIXES: tuple[str, ...] = (
    "assert",
    "_assert",
    "expect",
    "verify",
    "require",
    "check",
    "validate",
)
PYTEST_RESULT_CALLS: frozenset[str] = frozenset({"raises", "warns", "fail"})
# External validators whose exact method name raises when the response does not conform.
EXTERNAL_RESULT_CALLS: frozenset[str] = frozenset({"validate_response"})
GO_ERROR_METHODS = "Error|Errorf|Fatal|Fatalf|Fail|FailNow"
GO_FUNC_RE = re.compile(
    r"^func\s+(Test\w*)\s*\(\s*(\w+)\s+\*testing\.T\s*\)\s*\{", re.M
)
GO_FUNC_LITERAL_RE = re.compile(r"func\s*\(\s*(\w+)\s+\*testing\.T\s*\)\s*\{")


@dataclass(frozen=True)
class Block:
    path: str
    name: str
    line: int
    has_result_check: bool

    @property
    def key(self) -> str:
        return f"{self.path}::{self.name}"


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _is_trivial_test(node: ast.expr) -> bool:
    """True for ``assert <constant>`` and for a non-empty tuple of such constants."""
    if isinstance(node, ast.Constant):
        return True
    return (
        isinstance(node, ast.Tuple)
        and bool(node.elts)
        and all(_is_trivial_test(element) for element in node.elts)
    )


def _root_name(node: ast.expr) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


PythonFunction = ast.FunctionDef | ast.AsyncFunctionDef


def _is_fixture(function: PythonFunction) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if (isinstance(target, ast.Attribute) and target.attr == "fixture") or (
            isinstance(target, ast.Name) and target.id == "fixture"
        ):
            return True
    return False


def _python_references(function: PythonFunction) -> list[tuple[str, bool]]:
    """Names this function calls, plus parameters that may name a same-file fixture.

    Each entry is ``(name, is_parameter)``. A parameter reference only resolves to a
    fixture, so an ordinary function that happens to share a parameter's name is not
    treated as a helper.
    """
    references: list[tuple[str, bool]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name):
            references.append((callee.id, False))
        elif (
            isinstance(callee, ast.Attribute)
            and isinstance(callee.value, ast.Name)
            and callee.value.id in {"self", "cls"}
        ):
            references.append((callee.attr, False))
    arguments = function.args
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        references.append((argument.arg, True))
    return references


def _python_has_result_check(
    function: PythonFunction,
    imported: frozenset[str],
    pytest_bare: frozenset[str],
    definitions: dict[str, list[PythonFunction]] | None = None,
    stack: frozenset[int] = frozenset(),
    proven: set[int] | None = None,
) -> bool:
    """Return True when the block, or a same-file helper it uses, performs a check.

    A helper is resolved by name within the file. Every definition sharing that name
    must check, so a same-named helper without a check keeps the block flagged. The
    search follows helper calls transitively and stops at a cycle.
    """
    definitions = definitions or {}
    proven = proven if proven is not None else set()
    if id(function) in proven:
        return True
    if _direct_python_check(function, imported, pytest_bare, frozenset(definitions)):
        proven.add(id(function))
        return True
    active = stack | {id(function)}
    for name, is_parameter in _python_references(function):
        targets = [
            target
            for target in definitions.get(name, [])
            if not is_parameter or _is_fixture(target)
        ]
        if not targets or any(id(target) in active for target in targets):
            continue
        if all(
            _python_has_result_check(
                target, imported, pytest_bare, definitions, active, proven
            )
            for target in targets
        ):
            proven.add(id(function))
            return True
    return False


def _direct_python_check(
    function: PythonFunction,
    imported: frozenset[str],
    pytest_bare: frozenset[str],
    local_names: frozenset[str] = frozenset(),
) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Raise):
            exception = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exception, ast.Name) and exception.id == "AssertionError":
                return True
        if isinstance(node, ast.Assert):
            if not _is_trivial_test(node.test):
                return True
            continue
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Attribute):
            if (
                isinstance(callee.value, ast.Name)
                and callee.value.id in {"self", "cls"}
                and callee.attr in local_names
            ):
                continue
            if (
                isinstance(callee.value, ast.Name)
                and callee.value.id == "pytest"
                and callee.attr in PYTEST_RESULT_CALLS
            ):
                return True
            if callee.attr.startswith("assert") or callee.attr in EXTERNAL_RESULT_CALLS:
                return True
            root = _root_name(callee)
            if (
                callee.attr.startswith(HELPER_PREFIXES)
                and root is not None
                and (root in imported or root in {"self", "cls"})
            ):
                return True
        elif isinstance(callee, ast.Name):
            # Known helpers must prove their body, regardless of their name.
            if callee.id in local_names:
                continue
            if callee.id in pytest_bare or callee.id.startswith(HELPER_PREFIXES):
                return True
    return False


def python_blocks(relative_path: str, text: str) -> list[Block]:
    tree = ast.parse(text, filename=relative_path)
    imported: set[str] = set()
    pytest_bare: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                imported.add(bound)
                if node.module == "pytest" and alias.name in PYTEST_RESULT_CALLS:
                    pytest_bare.add(bound)
    definitions: dict[str, list[PythonFunction]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            definitions.setdefault(node.name, []).append(node)
    found: list[tuple[str, int, bool]] = []
    proven: set[int] = set()

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                child_scope = (*scope, child.name)
                # A fixture is a dependency, not a test block, even when its name starts with test_.
                if child.name.startswith("test_") and not _is_fixture(child):
                    found.append(
                        (
                            ".".join(child_scope),
                            child.lineno,
                            _python_has_result_check(
                                child,
                                frozenset(imported),
                                frozenset(pytest_bare),
                                definitions,
                                frozenset(),
                                proven,
                            ),
                        )
                    )
                visit(child, child_scope)
            elif isinstance(child, ast.ClassDef):
                visit(child, (*scope, child.name))
            else:
                visit(child, scope)

    visit(tree, ())
    return _with_unique_names(relative_path, found)


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def strip_go(text: str) -> str:
    """Return ``text`` with comments and string/rune literals blanked to spaces.

    Newlines are kept and the offsets of every remaining character are unchanged,
    so a match in the result can be mapped back to the original source.
    """
    out = list(text)
    length = len(text)

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            if out[index] != "\n":
                out[index] = " "

    index = 0
    while index < length:
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            blank(index, end)
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            blank(index, end)
            index = end
        elif text[index] in "\"'":
            quote = text[index]
            cursor = index + 1
            while cursor < length and text[cursor] not in (quote, "\n"):
                cursor += 2 if text[cursor] == "\\" else 1
            end = min(cursor + 1, length)
            blank(index, end)
            index = end
        elif text[index] == "`":
            end = text.find("`", index + 1)
            end = length if end == -1 else end + 1
            blank(index, end)
            index = end
        else:
            index += 1
    return "".join(out)


def _matching(code: str, open_index: int, opener: str = "{", closer: str = "}") -> int:
    depth = 0
    for index in range(open_index, len(code)):
        if code[index] == opener:
            depth += 1
        elif code[index] == closer:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"unbalanced {opener!r} at offset {open_index}")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _go_has_result_check(
    region: str, variable: str, local_names: frozenset[str] = frozenset()
) -> bool:
    var = re.escape(variable)
    patterns = (
        re.compile(r"(?<![\w.])(?:require|assert)\.\w+"),
        re.compile(rf"\b{var}\.(?:{GO_ERROR_METHODS})\s*\("),
    )
    if any(pattern.search(region) for pattern in patterns):
        return True
    helper_call = re.compile(
        rf"(?<![\w.])((?:assert|require|expect|check|verify)\w*)\s*\([^()]*\b{var}\b"
    )
    return any(
        match.group(1) not in local_names for match in helper_call.finditer(region)
    )


def _go_subtest_label(original: str, call_open: int, literal_start: int) -> str:
    raw = original[call_open + 1 : literal_start].strip().rstrip(",").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in '"`':
        return raw[1:-1]
    return raw or "<unnamed>"


GO_HELPER_DECL_RE = re.compile(
    r"^func\s+(\w+)\s*\(\s*(\w+)\s+\*testing\.T\b[^)]*\)", re.M
)


def _go_same_file_helpers(code: str) -> dict[str, tuple[str, int, int]]:
    """Map each top-level function that takes ``t *testing.T`` to its variable and body."""
    helpers: dict[str, tuple[str, int, int]] = {}
    for match in GO_HELPER_DECL_RE.finditer(code):
        open_index = code.index("{", match.end())
        helpers[match.group(1)] = (
            match.group(2),
            open_index,
            _matching(code, open_index),
        )
    return helpers


def _go_region_has_check(
    code: str,
    region: str,
    variable: str,
    helpers: dict[str, tuple[str, int, int]],
    stack: frozenset[str] = frozenset(),
) -> bool:
    """Return True when the region checks a result directly or through a same-file helper.

    A helper is a top-level function in the same file that takes ``t *testing.T`` and
    is called with that ``t``. The search follows helper calls transitively and stops
    at a cycle. A helper that is not in the file is not resolved.
    """
    if _go_has_result_check(region, variable, frozenset(helpers)):
        return True
    call = re.compile(rf"(?<![\w.])(\w+)\s*\([^()]*\b{re.escape(variable)}\b")
    for match in call.finditer(region):
        name = match.group(1)
        if name in stack or name not in helpers:
            continue
        helper_variable, open_index, close_index = helpers[name]
        if _go_region_has_check(
            code,
            code[open_index : close_index + 1],
            helper_variable,
            helpers,
            stack | {name},
        ):
            return True
    return False


def _collect_go_subtests(
    code: str,
    original: str,
    body_start: int,
    body_end: int,
    variable: str,
    prefix: str,
    relative_path: str,
    found: list[tuple[str, int, bool]],
    helpers: dict[str, tuple[str, int, int]],
) -> None:
    run_call = re.compile(rf"(?<![\w.]){re.escape(variable)}\.Run\s*\(")
    cursor = body_start
    while True:
        match = run_call.search(code, cursor, body_end)
        if match is None:
            return
        call_open = match.end() - 1
        call_close = _matching(code, call_open, "(", ")")
        literal = GO_FUNC_LITERAL_RE.search(code, call_open, call_close)
        if literal is None:
            cursor = match.end()
            continue
        literal_open = literal.end() - 1
        literal_close = _matching(code, literal_open)
        name = f"{prefix}/{_go_subtest_label(original, call_open, literal.start())}"
        found.append(
            (
                name,
                _line_of(original, match.start()),
                _go_region_has_check(
                    code,
                    code[literal_open : literal_close + 1],
                    literal.group(1),
                    helpers,
                ),
            )
        )
        _collect_go_subtests(
            code,
            original,
            literal_open,
            literal_close,
            literal.group(1),
            name,
            relative_path,
            found,
            helpers,
        )
        cursor = literal_close + 1


def go_blocks(relative_path: str, original: str) -> list[Block]:
    code = strip_go(original)
    helpers = _go_same_file_helpers(code)
    found: list[tuple[str, int, bool]] = []
    for match in GO_FUNC_RE.finditer(code):
        open_index = match.end() - 1
        close_index = _matching(code, open_index)
        name = match.group(1)
        found.append(
            (
                name,
                _line_of(original, match.start()),
                _go_region_has_check(
                    code, code[open_index : close_index + 1], match.group(2), helpers
                ),
            )
        )
        _collect_go_subtests(
            code,
            original,
            open_index,
            close_index,
            match.group(2),
            name,
            relative_path,
            found,
            helpers,
        )
    return _with_unique_names(relative_path, found)


def _with_unique_names(
    relative_path: str, found: list[tuple[str, int, bool]]
) -> list[Block]:
    """Keep names unique within a file by suffixing repeats with ``#2``, ``#3``."""
    seen: Counter[str] = Counter()
    blocks: list[Block] = []
    for name, line, checked in sorted(found, key=lambda entry: entry[1]):
        seen[name] += 1
        unique = name if seen[name] == 1 else f"{name}#{seen[name]}"
        blocks.append(Block(relative_path, unique, line, checked))
    return blocks


# ---------------------------------------------------------------------------
# Discovery, census and allowlist
# ---------------------------------------------------------------------------


def _python_files(root: Path) -> list[Path]:
    base = root / PYTHON_ROOT
    if not base.is_dir():
        return []
    return sorted(
        path
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts
        and (path.name.startswith("test_") or path.name.endswith("_test.py"))
    )


def _go_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory in GO_ROOTS:
        base = root / directory
        if base.is_dir():
            files.extend(
                path for path in base.rglob("*_test.go") if "vendor" not in path.parts
            )
    return sorted(files)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def run_census(root: Path) -> dict[str, Any]:
    languages: dict[str, dict[str, int]] = {}
    blocks: list[Block] = []
    errors: list[str] = []
    for language, files, scanner in (
        ("python", _python_files(root), python_blocks),
        ("go", _go_files(root), go_blocks),
    ):
        count = 0
        for path in files:
            relative = _relative(root, path)
            try:
                found = scanner(relative, path.read_text(encoding="utf-8"))
            except (SyntaxError, ValueError, UnicodeDecodeError) as error:
                errors.append(f"{relative}: {error}")
                continue
            count += 1
            blocks.extend(found)
        languages[language] = {
            "files": count,
            "blocks": sum(
                1 for block in blocks if _language_of(block.path) == language
            ),
            "with_result_check": sum(
                1
                for block in blocks
                if _language_of(block.path) == language and block.has_result_check
            ),
            "resultless": sum(
                1
                for block in blocks
                if _language_of(block.path) == language and not block.has_result_check
            ),
        }
    resultless = sorted(block.key for block in blocks if not block.has_result_check)
    return {
        "schema_version": SCHEMA_VERSION,
        "languages": languages,
        "totals": {
            key: sum(language[key] for language in languages.values())
            for key in ("files", "blocks", "with_result_check", "resultless")
        },
        "resultless": resultless,
        "errors": sorted(errors),
    }


def _language_of(path: str) -> str:
    return "python" if path.endswith(".py") else "go"


def load_allowlist(path: Path) -> dict[str, str]:
    """Return ``{path::name: reason}``. Raises ``ValueError`` on a malformed file."""
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        raise ValueError("allowlist must be an object with an 'entries' list")
    entries: dict[str, str] = {}
    for entry in document["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("allowlist entry must be an object")
        values = {}
        for field in ("path", "name", "reason"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"allowlist entry lacks a non-empty '{field}': {entry!r}"
                )
            values[field] = value
        key = f"{values['path']}::{values['name']}"
        if key in entries:
            raise ValueError(f"duplicate allowlist entry: {key}")
        entries[key] = values["reason"]
    return entries


def evaluate(census: dict[str, Any], allowlist: dict[str, str]) -> dict[str, Any]:
    resultless = set(census["resultless"])
    allowed = set(allowlist)
    report = dict(census)
    report["allowlisted"] = sorted(resultless & allowed)
    report["unlisted"] = sorted(resultless - allowed)
    report["stale_allowlist"] = sorted(allowed - resultless)
    report["allowlist_entries"] = len(allowed)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=REPOSITORY_ROOT, help="repository root"
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=DEFAULT_ALLOWLIST,
        help="reviewed allowlist file",
    )
    parser.add_argument(
        "--output", type=Path, help="write the JSON report to this path"
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    try:
        allowlist = load_allowlist(args.allowlist)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"test-block census: invalid allowlist: {error}", file=sys.stderr)
        return 1
    report = evaluate(run_census(root), allowlist)
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    totals = report["totals"]
    print(
        f"test-block census: files={totals['files']} blocks={totals['blocks']} "
        f"resultless={totals['resultless']} allowlisted={len(report['allowlisted'])} "
        f"unlisted={len(report['unlisted'])} stale={len(report['stale_allowlist'])} "
        f"errors={len(report['errors'])}",
        file=sys.stderr,
    )
    for key in report["unlisted"]:
        print(f"unlisted resultless block: {key}", file=sys.stderr)
    for key in report["stale_allowlist"]:
        print(f"stale allowlist entry: {key}", file=sys.stderr)
    for error in report["errors"]:
        print(f"unparsable test file: {error}", file=sys.stderr)
    failed = bool(report["unlisted"] or report["stale_allowlist"] or report["errors"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
