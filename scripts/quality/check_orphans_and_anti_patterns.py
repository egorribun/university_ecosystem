from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import json
import os
import posixpath
import re
import sys
import tokenize
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# Issue patterns in comments (e.g. QUALITY-123, TD-456, FIX-789, RZ-10-02)
ISSUE_PATTERN = re.compile(
    r"\b(QUALITY|TD|FIX|RZ|MOD|DESIGN|CQ|INFRA|A11Y)-\d+(\w+)?\b", re.IGNORECASE
)

_AUDIT_REGISTRY_HEADING = "## 7. Реестр открытых находок"
_AUDIT_ID_PATTERN = re.compile(r"(?<![\w-])AUD-[0-9]{3}(?![\w-])")


@lru_cache(maxsize=8)
def _registered_audit_ids(repository_root: Path) -> frozenset[str]:
    """Read one fail-closed registry snapshot per root during an inventory run."""
    try:
        registry = repository_root / "docs" / "audits" / "AUDIT-2026-10.md"
        lines = registry.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return frozenset()

    starts = [
        index for index, line in enumerate(lines) if line == _AUDIT_REGISTRY_HEADING
    ]
    if len(starts) != 1:
        return frozenset()
    start = starts[0] + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        None,
    )
    if end is None:
        return frozenset()
    # The authority prefix is plain Markdown, not fenced or commented examples.
    if any(
        line.lstrip().startswith(("```", "~~~")) or "<!--" in line or "-->" in line
        for line in lines[:end]
    ):
        return frozenset()

    registered: set[str] = set()
    for line in lines[start:end]:
        if line.startswith("|"):
            fields = line.split("|")
            identifier = fields[1].strip()
            description = fields[2].strip() if len(fields) > 2 else ""
        elif line.startswith("- "):
            fields = line[2:].split(maxsplit=1)
            identifier = fields[0] if fields else ""
            description = fields[1].strip() if len(fields) > 1 else ""
        else:
            continue
        if not identifier.lower().startswith("aud"):
            continue
        if _AUDIT_ID_PATTERN.fullmatch(identifier) is None or not description:
            return frozenset()
        registered.add(identifier)
    return frozenset(registered)


# Focused test markers
FOCUSED_TEST_PATTERNS = [
    (re.compile(r"\.only\b"), "JS/TS focused test marker (.only) found"),
    (re.compile(r"\bfit\("), "JS/TS focused test marker (fit) found"),
    (re.compile(r"\bfdescribe\("), "JS/TS focused test marker (fdescribe) found"),
    (
        re.compile(r"\bpytest\.mark\.only\b"),
        "Python focused test marker (@pytest.mark.only) found",
    ),
]

# Sleep patterns in tests
SLEEP_PATTERNS = [
    (re.compile(r"\btime\.sleep\("), "Python test sleep (time.sleep) found"),
    (re.compile(r"\btime\.Sleep\("), "Go test sleep (time.Sleep) found"),
    (re.compile(r"\bsetTimeout\("), "JS/TS test sleep (setTimeout) found"),
]

# Dynamic skip syntax. Python is parsed with its AST; Go and JavaScript use the
# existing comment/string masking plus syntax-shaped call matchers.
PYTHON_SKIP_MESSAGE = (
    "Python dynamic skip (pytest.skip/skip/mark.skip/mark.xfail) found"
)
GO_SKIP_PATTERNS = [
    (re.compile(r"\bt\.Skip\s*\("), "Go dynamic skip (t.Skip) found"),
    (re.compile(r"\bt\.Skipf\s*\("), "Go dynamic skip (t.Skipf) found"),
    (re.compile(r"\bt\.SkipNow\s*\("), "Go dynamic skip (t.SkipNow) found"),
]
JS_SKIP_PATTERNS = [
    (re.compile(r"\btest\s*\.\s*skip\s*\("), "JS/TS dynamic skip (test.skip) found"),
    (re.compile(r"\bit\s*\.\s*skip\s*\("), "JS/TS dynamic skip (it.skip) found"),
    (
        re.compile(r"\bdescribe\s*\.\s*skip\s*\("),
        "JS/TS dynamic skip (describe.skip) found",
    ),
]
OWNER_PATTERN = re.compile(r"(?<![\w])@[A-Za-z0-9][A-Za-z0-9_.-]*\b")

_TYPESCRIPT_FILE_REFERENCE = re.compile(
    r"\breadFileSync\s*\(\s*resolve\s*\(\s*process\.cwd\(\)\s*,\s*(?P<quote>['\"])(?P<path>[^'\"]+)(?P=quote)\s*\)",
    re.DOTALL,
)

_JS_LITERAL_PATTERN = r"\x00CODEX_JS_LITERAL_\d+\x00"
_JS_LITERAL_TOKEN = re.compile(_JS_LITERAL_PATTERN)
_JAVASCRIPT_MODULE_REFERENCE = re.compile(
    rf"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)"
    rf"(?P<path>{_JS_LITERAL_PATTERN})",
    re.DOTALL,
)
_JS_NEW_URL_REFERENCE = re.compile(
    r"\bnew\s+URL\s*\(\s*"
    rf"(?P<path>{_JS_LITERAL_PATTERN})\s*,\s*"
    r"(?P<base>import\.meta\.url|[A-Za-z_$][\w$]*)\s*\)"
)
_JS_URL_BASE = re.compile(
    r"\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*new\s+URL\s*\(\s*"
    rf"(?P<path>{_JS_LITERAL_PATTERN})\s*,\s*import\.meta\.url\s*\)"
)
_JS_READ_HELPER = re.compile(
    r"\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*\(\s*(?P<arg>[A-Za-z_$][\w$]*)\s*\)"
    r"\s*=>\s*readFile\s*\(\s*new\s+URL\s*\(\s*(?P=arg)\s*,\s*"
    r"(?P<base>import\.meta\.url|[A-Za-z_$][\w$]*)\s*\)"
)
_JS_PATH_RESOLVE_ROOT = re.compile(
    r"\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*path\.resolve\s*\(\s*"
    r"path\.dirname\s*\(\s*fileURLToPath\s*\(\s*import\.meta\.url\s*\)\s*\)"
    rf"(?P<segments>(?:\s*,\s*{_JS_LITERAL_PATTERN})+)\s*,?\s*\)"
)
_JS_IMPORT_META_DIRNAME_ROOT = re.compile(
    r"\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*path\.resolve\s*\(\s*"
    rf"import\.meta\.dirname\s*,\s*(?P<path>{_JS_LITERAL_PATTERN})\s*\)"
)
_JS_FILE_URL_DIRNAME = re.compile(
    r"\bconst\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*path\.dirname\s*\(\s*"
    r"fileURLToPath\s*\(\s*import\.meta\.url\s*\)\s*\)"
)
_JS_SCAN_ROOTS = re.compile(
    r"\bconst\s+scanRoots\s*=\s*\[(?P<values>[^\]]*)\]", re.DOTALL
)


def _js_regex_can_start(masked: list[str]) -> bool:
    prefix = "".join(masked).rstrip()
    if not prefix:
        return True
    match = re.search(r"([A-Za-z_$][\w$]*|=>|.)$", prefix)
    last_significant = match.group(1)
    if last_significant == ")":
        depth = 0
        for index in range(len(prefix) - 1, -1, -1):
            if prefix[index] == ")":
                depth += 1
            elif prefix[index] == "(":
                depth -= 1
                if depth == 0:
                    preceding = prefix[:index].rstrip()
                    return (
                        re.search(r"(?:^|[\s;{}:])(?:if|while|for|with)\s*$", preceding)
                        is not None
                    )
        # A closing parenthesis without a matching opener is malformed source.
        # Treat the following slash as opaque so malformed text cannot expose a
        # fake import to the reference matcher.
        return True
    return last_significant in {
        "return",
        "throw",
        "case",
        "delete",
        "void",
        "typeof",
        "instanceof",
        "in",
        "of",
        "yield",
        "await",
        "else",
        "do",
        "=",
        "(",
        "[",
        "{",
        ",",
        ";",
        ":",
        "?",
        "!",
        "~",
        "+",
        "-",
        "*",
        "%",
        "&",
        "|",
        "^",
        "<",
        ">",
        "=>",
    }


def _skip_javascript_regex(content: str, start: int) -> int:
    """Return the end of a regex literal, or the end of malformed source."""
    index = start + 1
    in_character_class = False
    while index < len(content):
        char = content[index]
        if char == "\\":
            index += 2
            continue
        if char in "\r\n":
            return len(content)
        if char == "[":
            in_character_class = True
        elif char == "]":
            in_character_class = False
        elif char == "/" and not in_character_class:
            index += 1
            while index < len(content) and content[index].isalpha():
                index += 1
            return index
        index += 1
    return len(content)


def _jsx_name_start_char(char: str) -> bool:
    return (
        char in "_$"
        or "A" <= char <= "Z"
        or "a" <= char <= "z"
        or (not char.isascii() and not char.isspace())
    )


def _jsx_name_continue_char(char: str) -> bool:
    return (
        char.isalnum() or char in "_$.:-" or (not char.isascii() and not char.isspace())
    )


def _match_jsx_opening_tag(content: str, start: int) -> tuple[str, int] | None:
    """Read a JSX opening name in one forward-only pass."""
    name_start = start + 1
    if (
        start < 0
        or start >= len(content)
        or content[start] != "<"
        or name_start >= len(content)
        or not _jsx_name_start_char(content[name_start])
    ):
        return None

    index = name_start + 1
    while index < len(content) and _jsx_name_continue_char(content[index]):
        index += 1
    if index == len(content) or not (
        content[index].isspace() or content[index] in "/><"
    ):
        return None
    return content[name_start:index], index


def _skip_jsx_string(content: str, start: int, nesting: int = 0) -> int | None:
    """Skip a JavaScript quoted value inside a JSX expression or type argument."""
    if nesting > 64:
        return None
    quote = content[start]
    index = start + 1
    while index < len(content):
        if content[index] == "\\":
            index += 2
            continue
        if quote == "`" and content.startswith("${", index):
            end = _skip_jsx_expression(content, index + 1, nesting + 1)
            if end is None:
                return None
            index = end
            continue
        if content[index] == quote:
            return index + 1
        if quote != "`" and content[index] in "\r\n":
            return None
        index += 1
    return None


def _skip_jsx_expression(content: str, start: int, nesting: int) -> int | None:
    """Balance one JSX expression; its contents cannot establish ownership."""
    if nesting > 64:
        return None
    depth = 1
    index = start + 1
    prefix: list[str] = []
    while index < len(content):
        if content.startswith("//", index):
            comment_end = content.find("\n", index + 2)
            if comment_end == -1:
                return None
            index = comment_end
            continue
        if content.startswith("/*", index):
            comment_end = content.find("*/", index + 2)
            if comment_end == -1:
                return None
            index = comment_end + 2
            continue
        char = content[index]
        if char in {"'", '"', "`"}:
            value_end = _skip_jsx_string(content, index, nesting + 1)
            if value_end is None:
                return None
            prefix.append(" value ")
            index = value_end
            continue
        if char == "<" and _js_regex_can_start(prefix):
            jsx_end = _skip_jsx_element(content, index, nesting + 1)
            if jsx_end is None:
                return None
            prefix.append(" value ")
            index = jsx_end
            continue
        if char == "/" and _js_regex_can_start(prefix):
            regex_end = _skip_javascript_regex(content, index)
            if regex_end >= len(content):
                return None
            prefix.append(" value ")
            index = regex_end
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        prefix.append(char)
        index += 1
    return None


def _skip_jsx_type_arguments(content: str, start: int, nesting: int) -> int | None:
    """Balance generic component arguments without exposing their text as code."""
    depth = 1
    index = start + 1
    while index < len(content):
        if nesting + depth > 64:
            return None
        if content.startswith("/*", index):
            comment_end = content.find("*/", index + 2)
            if comment_end == -1:
                return None
            index = comment_end + 2
            continue
        if content.startswith("//", index):
            comment_end = content.find("\n", index + 2)
            if comment_end == -1:
                return None
            index = comment_end
            continue
        char = content[index]
        if char in {"'", '"', "`"}:
            value_end = _skip_jsx_string(content, index, nesting + depth)
            if value_end is None:
                return None
            index = value_end
            continue
        if char == "<":
            depth += 1
        elif char == ">" and content[index - 1] != "=":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _skip_jsx_element(content: str, start: int, nesting: int = 0) -> int | None:
    """Recognize a balanced JSX subtree, not a relational-expression regex."""
    if nesting > 64:
        return None
    if content.startswith("<>", start):
        name = ""
        index = start + 2
    else:
        opening = _match_jsx_opening_tag(content, start)
        if opening is None:
            return None
        name, index = opening
        if content[index] == "<":
            arguments_end = _skip_jsx_type_arguments(content, index, nesting + 1)
            if arguments_end is None:
                return None
            index = arguments_end
        while index < len(content):
            if content.startswith("/>", index):
                return index + 2
            char = content[index]
            if char == ">":
                index += 1
                break
            if char in {"'", '"'}:
                # JSX attributes are multiline text, not JavaScript strings.
                # Backslashes do not escape their closing quote.
                quote_end = content.find(char, index + 1)
                if quote_end == -1:
                    return None
                index = quote_end + 1
                continue
            if char == "{":
                expression_end = _skip_jsx_expression(content, index, nesting + 1)
                if expression_end is None:
                    return None
                index = expression_end
                continue
            if char == "<":
                return None
            index += 1
        else:
            return None

    closing = re.compile(r"</" + re.escape(name) + r"\s*>")
    while index < len(content):
        if content.startswith("</", index):
            match = closing.match(content, index)
            return match.end() if match is not None else None
        if content[index] == "<":
            element_end = _skip_jsx_element(content, index, nesting + 1)
            if element_end is None:
                return None
            index = element_end
            continue
        if content[index] == "{":
            expression_end = _skip_jsx_expression(content, index, nesting + 1)
            if expression_end is None:
                return None
            index = expression_end
            continue
        index += 1
    return None


_STATIC_IMPORT_LINE_TERMINATOR = re.compile(r"[\r\n\u2028\u2029]")
_STATIC_IMPORT_BINDING = (
    r"(?!(?:await|break|case|catch|class|const|continue|debugger|default|delete|do"
    r"|else|enum|export|extends|false|finally|for|function|if|import|in|instanceof"
    r"|let|new|null|return|super|switch|this|throw|true|try|typeof|var|void|while"
    r"|with|yield|implements|interface|package|private|protected|public|static)\b)"
    r"[A-Za-z_$][A-Za-z0-9_$]*"
)
_STATIC_IMPORT_SPECIFIER = (
    rf"(?:type[ \t]+)?{_STATIC_IMPORT_BINDING}"
    rf"(?:[ \t]+as[ \t]+{_STATIC_IMPORT_BINDING})?"
)
_STATIC_IMPORT_NAMED = (
    rf"\{{[ \t]*(?:{_STATIC_IMPORT_SPECIFIER}"
    rf"(?:[ \t]*,[ \t]*{_STATIC_IMPORT_SPECIFIER})*[ \t]*,?)?[ \t]*\}}"
)
_LEADING_STATIC_IMPORT = re.compile(
    r"import[ \t]+"
    rf"(?:(?:type[ \t]+)?(?:{_STATIC_IMPORT_BINDING}"
    rf"|\*[ \t]+as[ \t]+{_STATIC_IMPORT_BINDING}|{_STATIC_IMPORT_NAMED})"
    r"[ \t]+from[ \t]+)?"
    r"(?P<quote>['\"])(?P<path>[^'\"\\\r\n\x00\u2028\u2029]+)(?P=quote)"
)


def _skip_static_import_trivia(content: str, start: int) -> int | None:
    """Skip only whitespace and closed comments, never arbitrary code."""
    index = start
    while index < len(content):
        if content[index] in " \t\r\n\u2028\u2029":
            index += 1
            continue
        if content.startswith("//", index):
            line_end = _STATIC_IMPORT_LINE_TERMINATOR.search(content, index + 2)
            index = len(content) if line_end is None else line_end.end()
            continue
        if content.startswith("/*", index):
            comment_end = content.find("*/", index + 2)
            if comment_end == -1:
                return None
            index = comment_end + 2
            continue
        return index
    return index


def _leading_static_imports(content: str) -> tuple[str, dict[str, str]]:
    """Preserve only a closed, leading single-line static-import block.

    This ownership fallback starts from raw source, not previously masked code:
    regex/division ambiguity in arbitrary code must never become import proof.
    Unsupported declarations or the first non-import statement end the block.
    """
    masked: list[str] = []
    literals: dict[str, str] = {}
    index = 0
    while (start := _skip_static_import_trivia(content, index)) is not None:
        if start >= len(content):
            break
        line_end = _STATIC_IMPORT_LINE_TERMINATOR.search(content, start)
        end = len(content) if line_end is None else line_end.start()
        line = content[start:end]
        declaration = _LEADING_STATIC_IMPORT.match(line)
        if declaration is None:
            break
        tail = declaration.end()
        while tail < len(line) and line[tail] in " \t":
            tail += 1
        terminated = tail < len(line) and line[tail] == ";"
        if terminated:
            tail += 1
        if _skip_static_import_trivia(line, tail) != len(line):
            break
        next_index = _skip_static_import_trivia(content, end)
        if next_index is None:
            break
        if not terminated and re.match(r"(?:with|assert)\b", content[next_index:]):
            # An attribute clause may continue on the next physical line.
            # Its grammar is outside this deliberately closed fallback.
            break
        token = f"\0CODEX_JS_LITERAL_{len(literals)}\0"
        literals[token] = declaration.group("path")
        masked.append(f"import {token};\n")
        index = end
    return "".join(masked), literals


def _mask_javascript_non_code(
    content: str, *, jsx: bool = False
) -> tuple[str, dict[str, str]]:
    """Replace comments, strings, templates, and regex literals before code matching."""
    # NUL is not valid in JavaScript source tokens. Reject it in raw source so
    # the private placeholders below cannot collide with code.
    if "\0" in content:
        return "", {}

    masked: list[str] = []
    literals: dict[str, str] = {}
    literal_index = 0
    index = 0
    while index < len(content):
        if content.startswith("//", index):
            end = content.find("\n", index + 2)
            if end == -1:
                end = len(content)
            masked.extend("\n" if char == "\n" else " " for char in content[index:end])
            index = end
            continue
        if content.startswith("/*", index):
            closing = content.find("*/", index + 2)
            end = len(content) if closing == -1 else closing + 2
            masked.extend("\n" if char == "\n" else " " for char in content[index:end])
            index = end
            continue
        if content[index] in {"'", '"', "`"}:
            quote = content[index]
            start = index
            index += 1
            closed = False
            while index < len(content):
                if content[index] == "\\":
                    index += 2
                    continue
                if content[index] == quote:
                    index += 1
                    closed = True
                    break
                if quote != "`" and content[index] in "\r\n":
                    break
                index += 1
            if not closed:
                return "", {}
            token = f"\0CODEX_JS_LITERAL_{literal_index}\0"
            literal_index += 1
            # Template text is opaque; it is not a static path literal here.
            if quote != "`":
                literals[token] = content[start + 1 : index - 1]
            masked.append(f" {token} ")
            continue
        if jsx and content[index] == "<" and _js_regex_can_start(masked):
            jsx_end = _skip_jsx_element(content, index)
            if jsx_end is None:
                # Discard arbitrary-code prefix tokens as well as this tail:
                # only fresh proof from leading static declarations survives.
                return _leading_static_imports(content[:index])
            # Ownership only: JSX text and attribute values are not imports.
            # Keep a value marker so a following slash remains division.
            masked.extend(
                "\n" if char == "\n" else " " for char in content[index:jsx_end]
            )
            masked.append(" jsx_value ")
            index = jsx_end
            continue
        if content[index] == "/" and _js_regex_can_start(masked):
            end = _skip_javascript_regex(content, index)
            if end > index + 1:
                masked.extend(
                    "\n" if char == "\n" else " " for char in content[index:end]
                )
                index = end
                continue
        masked.append(content[index])
        index += 1
    return "".join(masked), literals


def _javascript_string_values(text: str, literals: dict[str, str]) -> list[str]:
    return [
        literals[token]
        for token in _JS_LITERAL_TOKEN.findall(text)
        if token in literals
    ]


def _javascript_string_value(token: str, literals: dict[str, str]) -> str | None:
    return literals.get(token)


def _extract_braced_body(content: str, opening_brace: int) -> tuple[str, int] | None:
    depth = 0
    for index in range(opening_brace, len(content)):
        if content[index] == "{":
            depth += 1
        elif content[index] == "}":
            depth -= 1
            if depth == 0:
                return content[opening_brace + 1 : index], index + 1
    return None


def _collects_authored_files_recursively(
    content: str, literals: dict[str, str]
) -> tuple[set[str], set[str]] | None:
    function = re.search(
        r"\bfunction\s+collectAuthoredFiles\s*\(\s*(?P<root>[A-Za-z_$][\w$]*)\s*\)\s*\{",
        content,
    )
    if function is None:
        return None
    extracted = _extract_braced_body(content, function.end() - 1)
    if extracted is None:
        return None
    body, _ = extracted
    root_name = function.group("root")
    normalized = re.sub(r"\s+", "", body)
    guard = re.match(
        rf"if\(!fs\.existsSync\({re.escape(root_name)}\)\)return\[\];?",
        normalized,
    )
    if guard is not None:
        normalized = normalized[guard.end() :]
    if not normalized.startswith("constfiles=[]"):
        return None
    after_files = normalized[len("constfiles=[]") :]
    if after_files.startswith(";"):
        after_files = after_files[1:]
    loop = re.match(
        rf"for\(const(?P<entry>[A-Za-z_$][\w$]*)offs\.readdirSync\({re.escape(root_name)},\{{withFileTypes:true\}}\)\)\{{",
        after_files,
    )
    if loop is None:
        return None
    entry_name = loop.group("entry")
    expected_loop_body = (
        rf"if\({re.escape(entry_name)}\.isDirectory\(\)\)\{{"
        rf"if\(!ignoredDirectories\.has\({re.escape(entry_name)}\.name\)\)\{{"
        rf"files\.push\(\.\.\.collectAuthoredFiles\(path\.join\({re.escape(root_name)},{re.escape(entry_name)}\.name\)\)\);?"
        r"\}continue;?\}"
        rf"if\(authoredExtensions\.has\(path\.extname\({re.escape(entry_name)}\.name\)\)\)\{{"
        rf"files\.push\(path\.join\({re.escape(root_name)},{re.escape(entry_name)}\.name\)\);?"
        r"\}"
    )
    opening_brace = loop.end() - 1
    loop_body = _extract_braced_body(after_files, opening_brace)
    if loop_body is None or not re.fullmatch(expected_loop_body, loop_body[0]):
        return None
    suffix = after_files[loop_body[1] :]
    if not re.fullmatch(r"returnfiles;?", suffix):
        return None
    extension_set = re.search(
        r"\bconst\s+authoredExtensions\s*=\s*new\s+Set\s*\(\s*\[(?P<values>[^\]]*)\]\s*\)",
        content,
        re.DOTALL,
    )
    if extension_set is None:
        return None
    extensions = set(_javascript_string_values(extension_set.group("values"), literals))
    if not extensions:
        return None
    ignored_set = re.search(
        r"\bconst\s+ignoredDirectories\s*=\s*new\s+Set\s*\(\s*\[(?P<values>[^\]]*)\]\s*\)",
        content,
        re.DOTALL,
    )
    if ignored_set is None:
        return None
    ignored = set(_javascript_string_values(ignored_set.group("values"), literals))
    return extensions, ignored


def _walk_authored_files(
    root: Path, extensions: set[str], ignored: set[str], repository_root: Path
) -> set[Path]:
    """Mirror the proven Dirent recursion and return file paths, never directories."""
    found: set[Path] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in ignored:
                    pending.append(Path(entry.path))
                continue
            if Path(entry.name).suffix not in extensions or not entry.is_file(
                follow_symlinks=True
            ):
                continue
            file_path = Path(entry.path)
            try:
                resolved_file = file_path.resolve(strict=True)
                resolved_file.relative_to(repository_root)
            except (OSError, RuntimeError, ValueError):
                # The production reader follows file symlinks. Only retain the
                # lexical path when its resolved target stays inside the repo.
                continue
            found.add(file_path)
    return found


def _recursive_scan_references(
    content: str,
    file_path: Path,
    repository_root: Path,
    literals: dict[str, str],
) -> set[str]:
    frontend_root_match = _JS_IMPORT_META_DIRNAME_ROOT.search(content)
    scan_roots_match = _JS_SCAN_ROOTS.search(content)
    if frontend_root_match is None or scan_roots_match is None:
        return set()
    root_path = _javascript_string_value(frontend_root_match.group("path"), literals)
    if root_path is None:
        return set()
    collector = _collects_authored_files_recursively(content, literals)
    if collector is None:
        return set()

    root_loop = re.search(
        r"for\s*\(\s*const\s+root\s+of\s+scanRoots\s*\)\s*\{", content
    )
    if root_loop is None:
        return set()
    root_body = _extract_braced_body(content, root_loop.end() - 1)
    if root_body is None:
        return set()
    root_body_text = root_body[0]
    if not re.search(
        r"\bconst\s+absoluteRoot\s*=\s*path\.join\s*\(\s*frontendRoot\s*,\s*root\s*\)",
        root_body_text,
    ):
        return set()
    file_loop = re.search(
        r"for\s*\(\s*const\s+filePath\s+of\s+collectAuthoredFiles\s*\(\s*absoluteRoot\s*\)\s*\)\s*\{",
        root_body_text,
    )
    if file_loop is None:
        return set()
    file_body = _extract_braced_body(root_body_text, file_loop.end() - 1)
    file_body_text = "" if file_body is None else re.sub(r"\s+", "", file_body[0])
    if not re.match(
        rf"(?:const[A-Za-z_$][\w$]*=)?fs\.readFileSync\(filePath(?:,{_JS_LITERAL_PATTERN})?\);?",
        file_body_text,
    ):
        return set()

    frontend_root = (file_path.resolve().parent / root_path).resolve()
    try:
        frontend_root.relative_to(repository_root)
    except ValueError:
        return set()
    extensions, ignored = collector
    scan_roots = _javascript_string_values(scan_roots_match.group("values"), literals)
    references: set[str] = set()
    for scan_root in scan_roots:
        resolved = _js_target_path(
            scan_root, frontend_root, repository_root, allow_directory=True
        )
        if resolved is None:
            continue
        candidate = repository_root / resolved
        if not candidate.is_dir():
            continue
        for source_file in _walk_authored_files(
            candidate, extensions, ignored, repository_root
        ):
            references.add(source_file.relative_to(repository_root).as_posix())
    return references


def _js_target_path(
    target: str, base: Path, repository_root: Path, *, allow_directory: bool = False
) -> str | None:
    """Resolve a literal relative JS path without accepting aliases or dynamic values."""
    if (
        not target
        or target.startswith(("/", "\\"))
        or "\\" in target
        or "?" in target
        or "#" in target
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
    ):
        return None
    candidate = (base / target).resolve()
    try:
        relative = candidate.relative_to(repository_root)
    except ValueError:
        return None

    extensions = (".mjs", ".js", ".cjs", ".ts", ".tsx", ".jsx", ".json")
    candidates = [candidate]
    if not candidate.suffix:
        candidates.extend(candidate.with_suffix(extension) for extension in extensions)
        candidates.extend(candidate / f"index{extension}" for extension in extensions)
    for resolved in candidates:
        if not resolved.is_file():
            continue
        try:
            resolved_target = resolved.resolve(strict=True)
            resolved_target.relative_to(repository_root)
        except (OSError, RuntimeError, ValueError):
            continue
        return resolved_target.relative_to(repository_root).as_posix()
    if allow_directory and candidate.is_dir():
        return relative.as_posix()
    return None


def _js_url_base_directory(
    file_path: Path, target: str, repository_root: Path
) -> Path | None:
    if (
        not target
        or target.startswith(("/", "\\"))
        or "\\" in target
        or "?" in target
        or "#" in target
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
    ):
        return None
    resolved = (file_path.resolve().parent / target).resolve()
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        return None
    if target.endswith("/") or resolved.is_dir():
        return resolved
    return resolved.parent


def find_javascript_repository_references(file_path: Path) -> set[str]:
    """Return existing JS files statically imported or read by a JavaScript test.

    The reader follows only literal relative module/URL paths, the repository-root
    helpers used by release contracts, and one-argument ``read`` helpers whose
    implementation delegates to ``readFile(new URL(literal, base))``. It also
    records source directories only when the test recursively enumerates and reads
    each authored file below a literal scan-root list. The recursive scan records
    each matching file path it reads, never a source-root directory.
    """
    try:
        content, literals = _mask_javascript_non_code(
            file_path.read_text(encoding="utf-8")
        )
    except Exception:
        return set()

    repository_root = REPOSITORY_ROOT.resolve()
    references: set[str] = set()
    for match in _JAVASCRIPT_MODULE_REFERENCE.finditer(content):
        if content[: match.start()].rstrip().endswith("."):
            continue
        target = _javascript_string_value(match.group("path"), literals)
        if target is None:
            continue
        resolved = _js_target_path(target, file_path.resolve().parent, repository_root)
        if resolved:
            references.add(resolved)

    url_bases: dict[str, Path] = {}
    for match in _JS_URL_BASE.finditer(content):
        target = _javascript_string_value(match.group("path"), literals)
        if target is None:
            continue
        base = _js_url_base_directory(file_path, target, repository_root)
        if base is not None:
            url_bases[match.group("name")] = base

    static_bases: dict[str, Path] = dict(url_bases)
    for match in _JS_FILE_URL_DIRNAME.finditer(content):
        static_bases[match.group("name")] = file_path.resolve().parent
    for match in _JS_IMPORT_META_DIRNAME_ROOT.finditer(content):
        relative_base = _javascript_string_value(match.group("path"), literals)
        if relative_base is None:
            continue
        base = (file_path.resolve().parent / relative_base).resolve()
        try:
            base.relative_to(repository_root)
        except ValueError:
            continue
        static_bases[match.group("name")] = base

    for match in _JS_NEW_URL_REFERENCE.finditer(content):
        target = _javascript_string_value(match.group("path"), literals)
        if target is None:
            continue
        base_name = match.group("base")
        base = (
            file_path.resolve().parent
            if base_name == "import.meta.url"
            else url_bases.get(base_name)
        )
        if base is None:
            continue
        resolved = _js_target_path(target, base, repository_root)
        if resolved:
            references.add(resolved)

    for helper in _JS_READ_HELPER.finditer(content):
        helper_name = helper.group("name")
        base_name = helper.group("base")
        base = (
            file_path.resolve().parent
            if base_name == "import.meta.url"
            else url_bases.get(base_name)
        )
        if base is None:
            continue
        call_pattern = re.compile(
            rf"\b{re.escape(helper_name)}\s*\(\s*(?P<path>{_JS_LITERAL_PATTERN})\s*\)"
        )
        for call in call_pattern.finditer(content):
            target = _javascript_string_value(call.group("path"), literals)
            if target is None:
                continue
            resolved = _js_target_path(target, base, repository_root)
            if resolved:
                references.add(resolved)

    for root_match in _JS_PATH_RESOLVE_ROOT.finditer(content):
        root_name = root_match.group("name")
        segments = _javascript_string_values(root_match.group("segments"), literals)
        root = file_path.resolve().parent.joinpath(*segments).resolve()
        try:
            root.relative_to(repository_root)
        except ValueError:
            continue
        static_bases[root_name] = root

        # A literal JSON reader is a concrete dependency only if the helper
        # actually joins its literal argument under this statically derived root.
        helpers = re.finditer(
            r"\bfunction\s+(?P<name>[A-Za-z_$][\w$]*)\s*\(\s*(?P<arg>[A-Za-z_$][\w$]*)\s*\)\s*\{(?P<body>.*?)\}",
            content,
            re.DOTALL,
        )
        for function in helpers:
            if not re.search(
                rf"readFileSync\s*\(\s*path\.join\s*\(\s*{re.escape(root_name)}\s*,\s*{re.escape(function.group('arg'))}\s*\)",
                function.group("body"),
            ):
                continue
            call_pattern = re.compile(
                rf"\b{re.escape(function.group('name'))}\s*\(\s*(?P<path>{_JS_LITERAL_PATTERN})\s*\)"
            )
            for call in call_pattern.finditer(content):
                target = _javascript_string_value(call.group("path"), literals)
                if target is None:
                    continue
                resolved = _js_target_path(target, root, repository_root)
                if resolved:
                    references.add(resolved)

        # Direct path.join(root, "literal", ...) reads are also static.
        join_pattern = re.compile(
            rf"path\.join\s*\(\s*{re.escape(root_name)}(?P<tail>(?:\s*,\s*{_JS_LITERAL_PATTERN})+)\s*\)"
        )
        for join in join_pattern.finditer(content):
            segments = _javascript_string_values(join.group("tail"), literals)
            if segments:
                resolved = _js_target_path("/".join(segments), root, repository_root)
                if resolved:
                    references.add(resolved)

    # Resolve path.join(base, "literal", ...) when the base is itself statically
    # rooted at this test file or at a literal repository-relative URL.
    for base_name, base in static_bases.items():
        join_pattern = re.compile(
            rf"path\.join\s*\(\s*{re.escape(base_name)}(?P<tail>(?:\s*,\s*{_JS_LITERAL_PATTERN})+)\s*\)"
        )
        for join in join_pattern.finditer(content):
            segments = _javascript_string_values(join.group("tail"), literals)
            if not segments:
                continue
            resolved = _js_target_path(
                "/".join(segments), base, repository_root, allow_directory=True
            )
            if resolved:
                references.add(resolved)

    # Track recursive source-root scans only when the test declares literal roots,
    # iterates those roots, and reads files returned by its recursive enumerator.
    references.update(
        _recursive_scan_references(content, file_path, repository_root, literals)
    )
    return references


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify quality rules: check orphans, ownership, and anti-patterns."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "quality" / "inventory.json",
        help="Path to the generated inventory JSON manifest",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=REPOSITORY_ROOT / "quality" / "ownership-mapping.json",
        help="Path to ownership mapping configuration JSON",
    )
    return parser.parse_args(argv)


def safe_relative_path(file_path: Path) -> str:
    try:
        return str(file_path.relative_to(REPOSITORY_ROOT)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


class PythonTestVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, errors: list[str]) -> None:
        self.file_path = file_path
        self.errors = errors
        self.scopes: list[set[str]] = [set()]  # Scope stack, index 0 is module scope
        self.imported_modules: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scoped_body(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("test_"):
            current_scope = self.scopes[-1]
            if node.name in current_scope:
                self.errors.append(
                    f"ERROR: {safe_relative_path(self.file_path)}: "
                    f"duplicate test function '{node.name}' in the same scope"
                )
            current_scope.add(node.name)
        self._visit_scoped_body(node)

    def _visit_scoped_body(self, node: ast.AST) -> None:
        for field_name, value in ast.iter_fields(node):
            if field_name == "body":
                self.scopes.append(set())
                try:
                    for child in value:
                        self.visit(child)
                finally:
                    self.scopes.pop()
            elif isinstance(value, ast.AST):
                self.visit(value)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, ast.AST):
                        self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imported_modules.add(alias.name)
            self.imported_modules.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module
        if node.level:
            try:
                relative_path = self.file_path.resolve().relative_to(
                    REPOSITORY_ROOT.resolve()
                )
            except ValueError:
                relative_path = Path()
            package_parts = relative_path.parts[:-1]
            parent_count = node.level - 1
            if parent_count > len(package_parts):
                self.generic_visit(node)
                return
            package = package_parts[: len(package_parts) - parent_count]
            prefix = ".".join(package)
            module = ".".join(part for part in (prefix, module) if part)
        if module:
            self.imported_modules.add(module)
            self.imported_modules.add(module.split(".")[0])
            for alias in node.names:
                if alias.name != "*":
                    self.imported_modules.add(f"{module}.{alias.name}")
        self.generic_visit(node)


def check_python_duplicates_and_imports(file_path: Path, errors: list[str]) -> set[str]:
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        visitor = PythonTestVisitor(file_path, errors)
        visitor.visit(tree)
        return visitor.imported_modules
    except Exception:
        return set()


_REPOSITORY_ROOT_NAMES = frozenset(
    {"ROOT", "REPOSITORY_ROOT", "PROJECT_ROOT", "TEST_ROOT"}
)


def _repository_root_parent_index(node: ast.AST) -> int | None:
    if not isinstance(node, ast.Subscript):
        return None
    parents = node.value
    if not (
        isinstance(parents, ast.Attribute)
        and parents.attr == "parents"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
        and node.slice.value >= 0
    ):
        return None
    resolved = parents.value
    is_canonical = (
        isinstance(resolved, ast.Call)
        and not resolved.args
        and not resolved.keywords
        and isinstance(resolved.func, ast.Attribute)
        and resolved.func.attr == "resolve"
        and isinstance(resolved.func.value, ast.Call)
        and isinstance(resolved.func.value.func, ast.Name)
        and resolved.func.value.func.id == "Path"
        and len(resolved.func.value.args) == 1
        and isinstance(resolved.func.value.args[0], ast.Name)
        and resolved.func.value.args[0].id == "__file__"
    )
    return node.slice.value if is_canonical else None


def _is_valid_repository_root(node: ast.AST, file_path: Path) -> bool:
    parent_index = _repository_root_parent_index(node)
    if parent_index is None:
        return False
    try:
        resolved_parent = file_path.resolve().parents[parent_index]
    except IndexError:
        return False
    return resolved_parent == REPOSITORY_ROOT.resolve()


_NAMESPACE_MUTATION_METHODS = frozenset(
    {
        "__delitem__",
        "__init__",
        "__ior__",
        "__setitem__",
        "clear",
        "pop",
        "popitem",
        "setdefault",
        "update",
    }
)


def _is_direct_namespace_mapping(node: ast.AST, *, locals_are_module: bool) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "globals":
            return True
        if node.func.id == "locals":
            return locals_are_module
        if node.func.id == "vars":
            return bool(node.args or node.keywords) or locals_are_module
    # A lexical checker cannot prove which object owns an arbitrary __dict__.
    # Treat direct mutation through one as a possible module namespace write.
    return isinstance(node, ast.Attribute) and node.attr == "__dict__"


def _is_direct_dynamic_namespace_call(
    node: ast.Call, *, locals_are_module: bool
) -> bool:
    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
        return True
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in _NAMESPACE_MUTATION_METHODS
    ):
        return False
    if _is_direct_namespace_mapping(
        node.func.value, locals_are_module=locals_are_module
    ):
        return True
    return (
        isinstance(node.func.value, ast.Name)
        and node.func.value.id == "dict"
        and bool(node.args)
        and _is_direct_namespace_mapping(
            node.args[0], locals_are_module=locals_are_module
        )
    )


class _ComprehensionWalrusVisitor(ast.NodeVisitor):
    """Collect walrus targets that escape a module-level comprehension."""

    def __init__(self, names: set[str], module_effects: set[str]) -> None:
        self.names = names
        self.module_effects = module_effects

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if isinstance(node.target, ast.Name):
            self.names.add(node.target.id)
        self.visit(node.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # A lambda created inside the comprehension evaluates its defaults in
        # the comprehension's function scope; neither defaults nor body bind
        # names in the surrounding module.
        return

    def visit_Call(self, node: ast.Call) -> None:
        if _is_direct_dynamic_namespace_call(node, locals_are_module=False):
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and _is_direct_namespace_mapping(
            node.value, locals_are_module=False
        ):
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and node.attr == "__dict__":
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)


class _ModuleBindingVisitor(ast.NodeVisitor):
    """Collect bindings in the current module scope without entering child scopes."""

    def __init__(self, *, locals_are_module: bool = True) -> None:
        self.names: set[str] = set()
        self.module_effects: set[str] = set()
        self.locals_are_module = locals_are_module

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # ``name: Type`` records metadata in __annotations__, but does not bind
        # name. An annotated assignment with a value does bind its target.
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.target)
            self.visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_direct_dynamic_namespace_call(
            node, locals_are_module=self.locals_are_module
        ):
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and _is_direct_namespace_mapping(
            node.value, locals_are_module=self.locals_are_module
        ):
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)) and node.attr == "__dict__":
            self.module_effects.update(_REPOSITORY_ROOT_NAMES)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # ``except ... as name`` stores its target as a string rather than a
        # Name(Store) node, and deletes that binding when the handler exits.
        if node.name is not None:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name is not None:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.names.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest is not None:
            self.names.add(node.rest)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        self._visit_function_definition_expressions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)
        self._visit_function_definition_expressions(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        # Decorators, base classes, and class keywords are evaluated in the
        # defining module. The class body and type parameters have child scopes.
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self.module_effects.update(_class_module_effects(node))

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults are evaluated where the lambda is created; parameters and
        # its body belong to the lambda scope.
        self._visit_arguments_defaults(node.args)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, (node.key, node.value))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.names.update(_REPOSITORY_ROOT_NAMES)
            else:
                self.names.add(alias.asname or alias.name)

    def _visit_arguments_defaults(self, arguments: ast.arguments) -> None:
        for default in arguments.defaults:
            self.visit(default)
        for keyword_default in arguments.kw_defaults:
            if keyword_default is not None:
                self.visit(keyword_default)

    def _visit_function_definition_expressions(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self._visit_arguments_defaults(node.args)

    def _visit_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
        result_expressions: tuple[ast.expr, ...],
    ) -> None:
        if not node.generators:
            return
        # Python evaluates only the outermost iterable in the defining scope.
        # Comprehension targets are local, while PEP 572 walrus targets escape
        # every nested comprehension to the nearest non-comprehension scope.
        self.visit(node.generators[0].iter)
        walrus_visitor = _ComprehensionWalrusVisitor(self.names, self.module_effects)
        for expression in result_expressions:
            walrus_visitor.visit(expression)
        for index, generator in enumerate(node.generators):
            if index:
                walrus_visitor.visit(generator.iter)
            for condition in generator.ifs:
                walrus_visitor.visit(condition)


class _ExactScopeGlobalVisitor(ast.NodeVisitor):
    """Collect global declarations without descending into child code scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Global(self, node: ast.Global) -> None:
        self.names.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return


def _class_module_effects(node: ast.ClassDef) -> set[str]:
    globals_visitor = _ExactScopeGlobalVisitor()
    bindings_visitor = _ModuleBindingVisitor(locals_are_module=False)
    for statement in node.body:
        globals_visitor.visit(statement)
        bindings_visitor.visit(statement)
    return (
        bindings_visitor.names & globals_visitor.names
    ) | bindings_visitor.module_effects


def _module_binding_names(statement: ast.stmt) -> set[str]:
    visitor = _ModuleBindingVisitor()
    visitor.visit(statement)
    return visitor.names | visitor.module_effects


def _direct_root_assignment(
    statement: ast.stmt,
) -> tuple[str, ast.expr] | None:
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        return statement.targets[0].id, statement.value
    if (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.value is not None
    ):
        return statement.target.id, statement.value
    return None


def _static_repository_path_parts(
    node: ast.AST, repository_root_names: set[str], file_path: Path
) -> tuple[tuple[str, ...], bool] | None:
    """Resolve the static prefix of a repository-relative ``Path`` expression."""
    if _is_valid_repository_root(node, file_path):
        return (), False
    if isinstance(node, ast.Name) and node.id in repository_root_names:
        return (), False

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _static_repository_path_parts(
            node.left, repository_root_names, file_path
        )
        if left is None:
            return None
        left_parts, has_dynamic_suffix = left
        if has_dynamic_suffix:
            # Once a dynamic segment appears, its value may contain separators.
            # No later static segment can be proven repository-relative.
            return None
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            right = tuple(
                part
                for part in node.right.value.replace("\\", "/").split("/")
                if part not in {"", "."}
            )
            return left_parts + right, False
        # A dynamic final segment still leaves a useful, verifiable directory
        # prefix, e.g. ``ROOT / "alembic" / "versions" / migration_name``.
        return left_parts, True

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        value = node.args[0].value.replace("\\", "/")
        if re.match(r"^(?:[A-Za-z]:)?/", value):
            return None
        return (
            tuple(part for part in value.split("/") if part not in {"", "."}),
            False,
        )

    return None


class _FunctionScopeBindingVisitor(_ModuleBindingVisitor):
    """A bare annotation creates a function local, unlike a module binding."""

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)


def _repository_root_scope_bindings(tree: ast.AST) -> dict[ast.AST, set[str]]:
    """Collect root-name shadows in each child scope, never in its parent."""
    bindings: dict[ast.AST, set[str]] = {}
    for node in ast.walk(tree):
        visitor = (
            _FunctionScopeBindingVisitor(locals_are_module=False)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            else _ModuleBindingVisitor(locals_are_module=False)
        )
        arguments: ast.arguments | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for statement in node.body:
                visitor.visit(statement)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = node.args
        elif isinstance(node, ast.Lambda):
            visitor.visit(node.body)
            arguments = node.args
        elif isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            for generator in node.generators:
                visitor.visit(generator.target)
        else:
            continue
        if arguments is not None:
            visitor.names.update(
                argument.arg
                for argument in (
                    *arguments.posonlyargs,
                    *arguments.args,
                    *arguments.kwonlyargs,
                )
            )
            for argument in (arguments.vararg, arguments.kwarg):
                if argument is not None:
                    visitor.names.add(argument.arg)
        bindings[node] = (
            visitor.names | visitor.module_effects
        ) & _REPOSITORY_ROOT_NAMES
    return bindings


def _visible_repository_root_names(
    node: ast.AST,
    active_names: set[str],
    parents: dict[ast.AST, ast.AST],
    scope_bindings: dict[ast.AST, set[str]],
) -> set[str]:
    """Do not lend a module alias's proof to a different lexical binding."""
    visible = active_names.copy()
    class_scope_visible = True
    ancestors = {node}
    child = node
    while (parent := parents.get(child)) is not None:
        # PEP 695 introduces annotation scopes for generic functions, classes,
        # and type aliases. Conservatively shadow these names throughout the
        # declaration instead of borrowing a module alias's path proof.
        visible.difference_update(
            name
            for parameter in getattr(parent, "type_params", ())
            if isinstance(name := getattr(parameter, "name", None), str)
        )
        shadows = scope_bindings.get(parent, set())
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Defaults, decorators, and annotations are evaluated outside the
            # body scope. Bindings anywhere in a function body shadow throughout.
            if child in parent.body:
                visible.difference_update(shadows)
                class_scope_visible = False
        elif isinstance(parent, ast.ClassDef):
            if child in parent.body:
                if class_scope_visible:
                    visible.difference_update(shadows)
                # Methods and nested classes do not close over class locals.
                class_scope_visible = False
        elif isinstance(parent, ast.Lambda):
            if child is parent.body:
                visible.difference_update(shadows)
                class_scope_visible = False
        elif isinstance(
            parent, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            # Only the first iterable is evaluated in the enclosing scope.
            if parent.generators[0].iter not in ancestors:
                visible.difference_update(shadows)
                class_scope_visible = False
        ancestors.add(parent)
        child = parent
    return visible


def find_python_repository_references(file_path: Path) -> set[str]:
    """Return statically declared repository paths from a Python contract test.

    The lexical contract fails closed for wildcard imports and direct dynamic
    namespace operations (exec/eval, globals/locals/vars mappings, and direct
    ``__dict__`` mutation). It cannot prove the purity of arbitrary calls or
    follow namespace mappings through aliases; those are outside this static
    boundary and require the ordinary test/code-review gates.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except Exception:
        return set()

    binding_counts = {name: 0 for name in _REPOSITORY_ROOT_NAMES}
    canonical_statements: dict[str, ast.stmt] = {}
    for statement in tree.body:
        for name in _module_binding_names(statement) & _REPOSITORY_ROOT_NAMES:
            binding_counts[name] += 1
        assignment = _direct_root_assignment(statement)
        if (
            assignment is not None
            and assignment[0] in _REPOSITORY_ROOT_NAMES
            and _is_valid_repository_root(assignment[1], file_path)
        ):
            canonical_statements[assignment[0]] = statement

    authoritative_statements = {
        name: statement
        for name, statement in canonical_statements.items()
        if binding_counts[name] == 1
    }

    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    scope_bindings = _repository_root_scope_bindings(tree)
    active_root_names: set[str] = set()
    references: set[str] = set()
    for statement in tree.body:
        for node in ast.walk(statement):
            parent = parents.get(node)
            if (
                isinstance(parent, ast.BinOp)
                and isinstance(parent.op, ast.Div)
                and parent.left is node
            ):
                continue
            visible_roots = _visible_repository_root_names(
                node, active_root_names, parents, scope_bindings
            )
            resolved = _static_repository_path_parts(node, visible_roots, file_path)
            if resolved is not None and resolved[0]:
                references.add("/".join(resolved[0]))
        for name, binding_statement in authoritative_statements.items():
            if binding_statement is statement:
                active_root_names.add(name)
    return references


def _typescript_glob_references(
    file_path: Path, repository_root: Path, source: str
) -> set[str]:
    """Prove the closed local glob-and-read form used by source policy tests.

    Only the supported recursive pattern and exact ignore set are understood.
    Return actual files read by that traversal, never a directory-wide claim.
    """
    content, literals = _mask_javascript_non_code(source)
    # Escaped identifiers can denote a recognized binding with different raw
    # spelling. This closed grammar does not normalize them or borrow its proof.
    if "\\" in content:
        return set()
    required_imports = (
        (r"\{\s*readFileSync\s*\}", "node:fs"),
        (r"\{\s*fileURLToPath\s*\}", "node:url"),
        ("path", "node:path"),
        (r"\{\s*glob\s*\}", "glob"),
    )
    for binding, module in required_imports:
        matches = list(
            re.finditer(
                rf"\bimport\s+{binding}\s+from\s*"
                rf"(?P<module>{_JS_LITERAL_PATTERN})",
                content,
            )
        )
        if len(matches) != 1:
            return set()
        imported_module = _javascript_string_value(matches[0].group("module"), literals)
        if imported_module != module:
            return set()

    # Supplement the closed declaration/read sequence below with a binding-use
    # check. Extra declarations, assignments, parameter shadows, or overrides
    # cannot borrow another lexical binding's proof.
    expected_uses = {
        "readFileSync": 2,
        "fileURLToPath": 2,
        "path": 4,
        "glob": 2,
        "__filename": 2,
        "__dirname": 2,
        "SRC_ROOT": 3,
        "files": 3,
        "relFile": 2,
    }
    if any(
        len(re.findall(rf"\b{re.escape(name)}\b", content)) != count
        for name, count in expected_uses.items()
    ):
        return set()

    # A newline alone does not close an initializer: + and . can continue it.
    # Each separator below must lead directly to the next proven statement.
    separator = r"(?:[ \t\r]*;\s*|[ \t]*\r?\n\s*)"
    root_match = re.search(
        r"\bconst\s+__filename\s*=\s*fileURLToPath\s*\("
        rf"\s*import\.meta\.url\s*\){separator}"
        r"const\s+__dirname\s*=\s*path\.dirname\s*\(\s*__filename\s*\)"
        rf"{separator}const\s+SRC_ROOT\s*=\s*path\.resolve\s*\("
        rf"\s*__dirname\s*,\s*(?P<root>{_JS_LITERAL_PATTERN})\s*\)"
        rf"{separator}(?=const\b)",
        content,
    )
    glob_match = re.search(
        r"\bconst\s+files\s*=\s*await\s+glob\s*\(\s*"
        rf"(?P<pattern>{_JS_LITERAL_PATTERN})\s*,\s*\{{\s*"
        r"cwd\s*:\s*SRC_ROOT\s*,\s*ignore\s*:\s*\["
        rf"\s*(?P<ignores>{_JS_LITERAL_PATTERN}"
        rf"(?:\s*,\s*{_JS_LITERAL_PATTERN})*\s*,?)\s*\]"
        r"\s*,?\s*\}\s*\)",
        content,
    )
    reader_match = re.search(
        r"\bconst\s+[A-Za-z_$][\w$]*\s*=\s*"
        r"files\.filter\s*\(\s*\(\s*relFile\s*\)\s*=>\s*"
        r"[A-Za-z_$][\w$]*\.test\s*\(\s*readFileSync\s*\(\s*"
        r"path\.join\s*\(\s*SRC_ROOT\s*,\s*relFile\s*\)\s*,\s*"
        rf"(?P<encoding>{_JS_LITERAL_PATTERN})\s*\)\s*\)\s*\)",
        content,
    )
    if root_match is None or glob_match is None or reader_match is None:
        return set()
    if not root_match.end() < glob_match.start() < reader_match.start():
        return set()
    between_statements = re.fullmatch(
        rf"{separator}expect\s*\(\s*files\.length\s*\)"
        rf"\.toBeGreaterThan\s*\(\s*0\s*\){separator}",
        content[glob_match.end() : reader_match.start()],
    )
    if between_statements is None:
        return set()

    # The root proof belongs to module scope, not a similarly named local in an
    # unrelated block/function. Strings, comments, and regexes are already opaque.
    delimiters: list[str] = []
    closing_delimiters = {")": "(", "]": "[", "}": "{"}
    for char in content[: root_match.start()]:
        if char in "([{":
            delimiters.append(char)
        elif char in closing_delimiters:
            if not delimiters or delimiters.pop() != closing_delimiters[char]:
                return set()
    if delimiters:
        return set()

    glob_pattern = _javascript_string_value(glob_match.group("pattern"), literals)
    if glob_pattern != "**/*.{ts,tsx,css}":
        return set()
    if _javascript_string_value(reader_match.group("encoding"), literals) not in {
        "utf-8",
        "utf8",
    }:
        return set()
    ignored_patterns = _javascript_string_values(glob_match.group("ignores"), literals)
    supported_ignores = {
        "tests/**",
        "**/__tests__/**",
        "**/*.test.{ts,tsx}",
        "**/*.spec.{ts,tsx}",
        "**/*.stories.{ts,tsx}",
    }
    if (
        len(ignored_patterns) != len(supported_ignores)
        or set(ignored_patterns) != supported_ignores
    ):
        return set()

    relative_root = _javascript_string_value(root_match.group("root"), literals)
    if relative_root is None:
        return set()
    root_path = _js_target_path(
        relative_root,
        file_path.resolve().parent,
        repository_root,
        allow_directory=True,
    )
    if root_path is None:
        return set()
    root = repository_root / root_path
    if not root.is_dir():
        return set()

    references: set[str] = set()
    for candidate in _walk_authored_files(
        root, {".ts", ".tsx", ".css"}, {"__tests__"}, repository_root
    ):
        relative = candidate.relative_to(root)
        if relative.parts[0] == "tests" or any(
            part.startswith(".") for part in relative.parts
        ):
            continue
        if candidate.suffix in {".ts", ".tsx"} and candidate.stem.endswith(
            (".test", ".spec", ".stories")
        ):
            continue
        references.add(candidate.relative_to(repository_root).as_posix())
    return references


def find_typescript_repository_references(file_path: Path) -> set[str]:
    """Return static package-relative files read by a TypeScript contract test."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return set()

    repository_root = REPOSITORY_ROOT.resolve()
    package_root = next(
        (
            parent.resolve()
            for parent in file_path.resolve().parents
            if parent == repository_root or repository_root in parent.parents
            if (parent / "package.json").is_file()
        ),
        None,
    )
    if package_root is None:
        return set()

    references = _typescript_glob_references(file_path, repository_root, content)
    for match in _TYPESCRIPT_FILE_REFERENCE.finditer(content):
        target = match.group("path")
        if (
            not target
            or target.startswith(("/", "\\"))
            or "\\" in target
            or "?" in target
            or "#" in target
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
        ):
            continue
        candidate = (package_root / target).resolve()
        try:
            relative = candidate.relative_to(repository_root)
        except ValueError:
            continue
        references.add(relative.as_posix())
    return references


def _references_inventory_target(
    repository_references: set[str], reference_paths: set[str]
) -> bool:
    for reference in repository_references:
        normalized = reference.replace("\\", "/").rstrip("/")
        if not normalized:
            continue
        if any(
            candidate == normalized or candidate.startswith(normalized + "/")
            for candidate in reference_paths
        ):
            return True
    return False


def _mask_go_comments_and_literals(content: str) -> str:
    masked = list(content)
    length = len(content)
    index = 0

    def blank(start: int, end: int, *, literal: bool = False) -> None:
        marker_written = False
        for position in range(start, end):
            if content[position] in "\r\n":
                continue
            if literal and not marker_written:
                masked[position] = "\0"
                marker_written = True
            else:
                masked[position] = " "

    while index < length:
        if content.startswith("//", index):
            end = content.find("\n", index + 2)
            if end == -1:
                end = length
            blank(index, end)
            index = end
            continue

        if content.startswith("/*", index):
            closing = content.find("*/", index + 2)
            end = length if closing == -1 else closing + 2
            blank(index, end)
            index = end
            continue

        quote = content[index]
        if quote in {'"', "'", "`"}:
            end = index + 1
            while end < length:
                current = content[end]
                if quote != "`" and current == "\\":
                    end += 2
                    continue
                if current == quote:
                    end += 1
                    break
                if quote != "`" and current in "\r\n":
                    break
                end += 1
            blank(index, min(end, length), literal=True)
            index = max(end, index + 1)
            continue

        index += 1

    return "".join(masked)


def check_go_duplicates(file_path: Path, errors: list[str]) -> None:
    try:
        content = file_path.read_text(encoding="utf-8")
        content = _mask_go_comments_and_literals(content)
        pattern = re.compile(r"\bfunc\s+(Test\w+)\b")
        seen_funcs = set()
        for match in pattern.finditer(content):
            func_name = match.group(1)
            if func_name in seen_funcs:
                errors.append(
                    f"ERROR: {safe_relative_path(file_path)}: duplicate test function name '{func_name}'"
                )
            seen_funcs.add(func_name)
    except Exception:  # noqa: S110
        pass


def matches_any_glob(path_str: str, patterns: list[str]) -> bool:
    posix_path = path_str.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatchcase(posix_path, pattern) or fnmatch.fnmatchcase(
            Path(posix_path).name, pattern
        ):
            return True
    return False


def _python_attribute_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _python_attribute_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent is not None else None
    return None


def _python_skip_sites(content: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []

    aliases: dict[str, str] = {"pytest": "pytest"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest":
                    aliases[alias.asname or "pytest"] = "pytest"
        elif isinstance(node, ast.ImportFrom) and node.module == "pytest":
            for alias in node.names:
                if alias.name in {"skip", "mark"}:
                    aliases[alias.asname or alias.name] = f"pytest.{alias.name}"

    sites: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and _python_attribute_name(node.func, aliases) == "pytest.skip"
        ):
            sites.add((node.lineno, PYTHON_SKIP_MESSAGE))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                expression = (
                    decorator.func if isinstance(decorator, ast.Call) else decorator
                )
                if _python_attribute_name(expression, aliases) in {
                    "pytest.mark.skip",
                    "pytest.mark.xfail",
                }:
                    sites.add((decorator.lineno, PYTHON_SKIP_MESSAGE))
    return sorted(sites)


def _python_comments_by_line(content: str) -> dict[int, list[str]]:
    comments: dict[int, list[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comments.setdefault(token.start[0], []).append(token.string)
    except (IndentationError, tokenize.TokenError):
        pass
    return comments


def _c_style_comments_by_line(
    content: str, *, javascript: bool
) -> dict[int, list[str]]:
    comments: dict[int, list[str]] = {}
    masked: list[str] = []
    index = 0
    line = 1
    length = len(content)

    def mask_span(start: int, end: int) -> None:
        nonlocal line
        for char in content[start:end]:
            masked.append("\n" if char == "\n" else " ")
            if char == "\n":
                line += 1

    while index < length:
        if content.startswith("//", index):
            end = content.find("\n", index + 2)
            if end == -1:
                end = length
            comments.setdefault(line, []).append(content[index + 2 : end])
            mask_span(index, end)
            index = end
            continue
        if content.startswith("/*", index):
            closing = content.find("*/", index + 2)
            end = length if closing == -1 else closing + 2
            comment_end = length if closing == -1 else closing
            for offset, comment_line in enumerate(
                content[index + 2 : comment_end].splitlines()
            ):
                comments.setdefault(line + offset, []).append(comment_line)
            mask_span(index, end)
            index = end
            continue
        quote = content[index]
        if quote in {"'", '"', "`"}:
            start = index
            index += 1
            while index < length:
                if content[index] == "\\" and (javascript or quote != "`"):
                    index += 2
                    continue
                if content[index] == quote:
                    index += 1
                    break
                if quote != "`" and content[index] in "\r\n":
                    break
                index += 1
            mask_span(start, min(index, length))
            continue
        if javascript and quote == "/" and _js_regex_can_start(masked):
            end = _skip_javascript_regex(content, index)
            if end > index + 1:
                mask_span(index, end)
                index = end
                continue
        masked.append(content[index])
        if content[index] == "\n":
            line += 1
        index += 1
    return comments


def _dynamic_skip_sites(file_path: Path, content: str) -> list[tuple[int, str]]:
    suffix = file_path.suffix.lower()
    if suffix == ".py":
        return _python_skip_sites(content)

    if suffix == ".go":
        masked = _mask_go_comments_and_literals(content)
        patterns = GO_SKIP_PATTERNS
    elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
        masked, _ = _mask_javascript_non_code(content)
        patterns = JS_SKIP_PATTERNS
    else:
        return []

    sites: set[tuple[int, str]] = set()
    for pattern, message in patterns:
        for match in pattern.finditer(masked):
            line = masked.count("\n", 0, match.start()) + 1
            sites.add((line, message))
    return sorted(sites)


def _has_skip_tracking_comment(line: int, comments: dict[int, list[str]]) -> bool:
    evidence = "\n".join(comments.get(line, []) + comments.get(line - 1, []))
    if OWNER_PATTERN.search(evidence) is None:
        return False
    if ISSUE_PATTERN.search(evidence) is not None:
        return True
    return any(
        match.group() in _registered_audit_ids(REPOSITORY_ROOT)
        for match in _AUDIT_ID_PATTERN.finditer(evidence)
    )


def check_anti_patterns(
    file_path: Path,
    errors: list[str],
    allowed_sleeps: list[str],
    allowed_dynamic_skips: list[str],
) -> None:
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
    except Exception as error:
        errors.append(f"ERROR: unable to read {safe_relative_path(file_path)}: {error}")
        return

    path_str = safe_relative_path(file_path)
    is_sleep_allowed = matches_any_glob(path_str, allowed_sleeps)
    is_skip_allowed = matches_any_glob(path_str, allowed_dynamic_skips)

    for line_idx, line in enumerate(lines, 1):
        line_clean = line.strip()
        # Skip commented out lines
        if line_clean.startswith(("#", "//", "/*", "*")):
            continue

        # 1. Focused test markers
        for regex, msg in FOCUSED_TEST_PATTERNS:
            if regex.search(line):
                errors.append(f"ERROR: {path_str}:L{line_idx}: {msg}")

        # 2. Unbounded sleeps
        if not is_sleep_allowed:
            for regex, msg in SLEEP_PATTERNS:
                if regex.search(line):
                    # Check for allowlist / bound comment in same or adjacent line
                    has_allowlist = (
                        "pragma: allowlist" in line
                        or "bound" in line.lower()
                        or "retry" in line.lower()
                    )
                    # Check if preceding line has pragma
                    if line_idx > 1 and (
                        "pragma: allowlist" in lines[line_idx - 2]
                        or "bound" in lines[line_idx - 2].lower()
                    ):
                        has_allowlist = True
                    if not has_allowlist:
                        errors.append(
                            f"ERROR: {path_str}:L{line_idx}: {msg} without explicit bound or retry pragma"
                        )

    if not is_skip_allowed:
        if file_path.suffix.lower() == ".py":
            comments = _python_comments_by_line(content)
        else:
            comments = _c_style_comments_by_line(
                content,
                javascript=file_path.suffix.lower()
                in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"},
            )
        for line_idx, message in _dynamic_skip_sites(file_path, content):
            if not _has_skip_tracking_comment(line_idx, comments):
                errors.append(
                    f"ERROR: {path_str}:L{line_idx}: {message} requires tracking issue (e.g. QUALITY-123) and owner (@username) in comment"
                )


def _python_module_inventory_paths(imported_modules: set[str]) -> set[str]:
    paths: set[str] = set()
    for module in imported_modules:
        normalized = module.replace(".", "/").replace("\\", "/").strip("/")
        if not normalized or any(part in {".", ".."} for part in normalized.split("/")):
            continue
        paths.add(f"{normalized}.py")
        paths.add(f"{normalized}/__init__.py")
    return paths


def _typescript_import_targets(test_path: str, reference_paths: set[str]) -> bool:
    normalized_test_path = test_path.replace("\\", "/")
    test_file = REPOSITORY_ROOT.joinpath(*PurePosixPath(normalized_test_path).parts)
    try:
        content = test_file.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False

    masked, literals = _mask_javascript_non_code(
        content, jsx=normalized_test_path.endswith(".tsx")
    )
    for match in _JAVASCRIPT_MODULE_REFERENCE.finditer(masked):
        specifier = _javascript_string_value(match.group("path"), literals)
        if not specifier:
            continue
        if specifier.startswith("@/"):
            base = PurePosixPath("frontend/src")
            module_path = specifier[2:]
        elif specifier.startswith(("./", "../")):
            base = PurePosixPath(normalized_test_path).parent
            module_path = specifier
        else:
            continue

        resolved = posixpath.normpath((base / module_path).as_posix())
        if (
            resolved in {".", ".."}
            or resolved.startswith("../")
            or resolved.startswith("/")
        ):
            continue
        candidates = {resolved}
        extensions = (
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
            ".mts",
            ".cts",
            ".json",
        )
        if PurePosixPath(resolved).suffix not in extensions:
            candidates.update(f"{resolved}{extension}" for extension in extensions)
            candidates.update(
                f"{resolved}/index{extension}" for extension in extensions
            )
        if candidates.intersection(reference_paths):
            return True
    return False


def _go_package_name(file_path: Path) -> str | None:
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    masked = _mask_go_comments_and_literals(content)
    match = re.search(r"(?m)^\s*package\s+([A-Za-z_]\w*)\b", masked)
    return match.group(1) if match else None


def matches_source(
    test_path: str,
    source_paths: set[str],
    allowed_orphans: list[str],
    imported_modules: set[str] | None = None,
    workflow_paths: set[str] | None = None,
    repository_references: set[str] | None = None,
    reference_paths: set[str] | None = None,
    contract_test_paths: set[str] | None = None,
) -> bool:
    test_path = test_path.replace("\\", "/")
    if matches_any_glob(test_path, allowed_orphans):
        return True

    # These directories are explicit classifications with their own quality
    # contracts; all other tests need a concrete inventoried relationship.
    allowed_folders = {
        "tests/integration",
        "tests/chaos",
        "tests/contracts",
        "tests/performance",
        "tests/fuzz",
    }
    if any(test_path.startswith(folder + "/") for folder in allowed_folders):
        return True

    generic_reference_paths = reference_paths or set()
    if test_path.endswith(".test.mjs"):
        # A Playwright spec is usable only through the exact contract matcher.
        generic_reference_paths = generic_reference_paths - (
            contract_test_paths or set()
        )
    if repository_references and _references_inventory_target(
        repository_references, generic_reference_paths
    ):
        return True

    if (
        test_path.endswith(".test.mjs")
        and re.search(r"(?:^|[.-])contract\.test\.mjs$", Path(test_path).name)
        and repository_references
        and repository_references.intersection(contract_test_paths or set())
    ):
        return True

    path_obj = Path(test_path)
    name = path_obj.name

    if (
        test_path.startswith("tests/")
        and name.startswith("test_")
        and test_path.endswith(".py")
    ):
        if imported_modules and reference_paths:
            if _python_module_inventory_paths(imported_modules).intersection(
                reference_paths
            ):
                return True

        base_stem = name[len("test_") : -len(".py")]
        common_suffixes = (
            "_service",
            "_api",
            "_full",
            "_coverage",
            "_unit",
            "_booster",
        )
        candidate_stems = [base_stem]
        while candidate_stems:
            current_stem = candidate_stems[-1]
            next_stem = next(
                (
                    current_stem[: -len(suffix)]
                    for suffix in common_suffixes
                    if current_stem.endswith(suffix) and len(current_stem) > len(suffix)
                ),
                None,
            )
            if next_stem is None:
                break
            candidate_stems.append(next_stem)

        for candidate_stem in candidate_stems:
            naming_matches: set[str] = set()
            for source in source_paths:
                source_path = PurePosixPath(source.replace("\\", "/"))
                if source_path.suffix != ".py":
                    continue
                if source_path.stem == candidate_stem or (
                    source_path.name == "__init__.py"
                    and source_path.parent.name == candidate_stem
                ):
                    naming_matches.add(source_path.as_posix())
            if naming_matches:
                return len(naming_matches) == 1

        workflow_name = name[len("test_") : -len(".py")].removesuffix(
            "_workflow_contract"
        )
        if workflow_name != name[len("test_") : -len(".py")] and any(
            PurePosixPath(workflow_path).parent == PurePosixPath(".github/workflows")
            and PurePosixPath(workflow_path).suffix in {".yml", ".yaml"}
            and PurePosixPath(workflow_path).stem.replace("-", "_") == workflow_name
            for workflow_path in workflow_paths or set()
        ):
            return True
        return False

    if test_path.endswith((".test.ts", ".test.tsx")):
        import_targets = source_paths | (reference_paths or set())
        if _typescript_import_targets(test_path, import_targets):
            return True

        if name.endswith(".test.tsx"):
            test_stem = name[: -len(".test.tsx")]
        else:
            test_stem = name[: -len(".test.ts")]
        test_stem = re.sub(r"\.(?:branches|booster|closure|edge)$", "", test_stem)
        source_stems = (f"{test_stem}.ts", f"{test_stem}.tsx")
        nearby_source_dirs = {PurePosixPath(test_path).parent}
        if PurePosixPath(test_path).parent.name == "__tests__":
            nearby_source_dirs.add(PurePosixPath(test_path).parent.parent)
        for source in source_paths:
            source_path = PurePosixPath(source.replace("\\", "/"))
            if source_path.parent not in nearby_source_dirs:
                continue
            if source_path.name in source_stems:
                return True
            source_stem = source_path.stem
            if source_path.suffix in {".ts", ".tsx"} and test_stem.startswith(
                source_stem + "."
            ):
                return True
        return False

    if test_path.endswith(".test.mjs"):
        test_stem = name.removesuffix(".test.mjs")
        nearby_source_dirs = {
            PurePosixPath(test_path).parent,
            PurePosixPath(test_path).parent.parent,
        }
        for source in source_paths:
            source_path = PurePosixPath(source.replace("\\", "/"))
            if (
                source_path.parent in nearby_source_dirs
                and source_path.suffix in {".mjs", ".js", ".cjs"}
                and source_path.stem == test_stem
            ):
                return True
        return False

    if test_path.endswith("_test.go"):
        test_package = _go_package_name(REPOSITORY_ROOT / test_path)
        test_directory = PurePosixPath(test_path).parent
        package_paths = source_paths | (reference_paths or set())
        if test_package:
            for source in package_paths:
                normalized_source = source.replace("\\", "/")
                source_path = PurePosixPath(normalized_source)
                if source_path.parent != test_directory or source_path.suffix != ".go":
                    continue
                source_package = _go_package_name(REPOSITORY_ROOT / normalized_source)
                if source_package and test_package in {
                    source_package,
                    f"{source_package}_test",
                }:
                    return True
        return False

    return False


def _inventory_validation_error(manifest: object) -> str | None:
    """Validate the generated fields consumed by the quality checks."""
    if not isinstance(manifest, dict):
        return "manifest must be an object"
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return "files must be a non-empty list"
    for index, record in enumerate(files):
        location = f"files[{index}]"
        if not isinstance(record, dict):
            return f"{location} must be an object"
        path = record.get("path")
        if (
            not isinstance(path, str)
            or not path
            or "\\" in path
            or not PurePosixPath(path).name
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
        ):
            return f"{location}.path must be a non-empty repository-relative POSIX file path"
        classification = record.get("classification")
        if not isinstance(classification, str) or classification not in {
            "source",
            "test",
            "generated",
            "utility",
        }:
            return (
                f"{location}.classification must be source, test, generated, or utility"
            )
        owner = record.get("owner")
        if "owner" not in record or (
            owner is not None and (not isinstance(owner, str) or not owner.strip())
        ):
            return f"{location}.owner must be a non-empty string or null"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    _registered_audit_ids.cache_clear()
    args = _parse_arguments(argv)

    if not args.inventory.exists():
        print(
            f"ERROR: inventory manifest not found at {args.inventory}. Run generate_test_inventory.py first.",
            file=sys.stderr,
        )
        return 2

    if not args.mapping.exists():
        print(
            f"ERROR: ownership mapping file not found at {args.mapping}",
            file=sys.stderr,
        )
        return 2

    try:
        manifest = json.loads(args.inventory.read_text(encoding="utf-8"))
        mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    except Exception as parse_error:
        print(
            f"ERROR: failed to parse config/manifest: {parse_error}",
            file=sys.stderr,
        )
        return 2

    if validation_error := _inventory_validation_error(manifest):
        print(f"ERROR: invalid inventory manifest: {validation_error}", file=sys.stderr)
        return 2

    allowed_sleeps = mapping.get("allowed_sleeps", [])
    allowed_dynamic_skips = mapping.get("allowed_dynamic_skips", [])
    allowed_orphans = mapping.get("allowed_orphans", [])

    files = manifest["files"]
    errors = []

    source_paths = {f["path"] for f in files if f["classification"] == "source"}
    reference_paths = {f["path"] for f in files if f["classification"] != "test"}
    # Workflows are classified as utilities. Keep them separate from ordinary
    # source paths so only the exact workflow-contract matcher may use them.
    workflow_paths = {
        f["path"]
        for f in files
        if f["path"].startswith(".github/workflows/")
        and f["path"].endswith((".yml", ".yaml"))
    }
    contract_test_paths = {
        f["path"] for f in files if f["path"].endswith((".spec.ts", ".spec.tsx"))
    }

    for f in files:
        path_str = f["path"]
        classification = f["classification"]
        owner = f["owner"]

        file_path = REPOSITORY_ROOT / path_str
        if not file_path.exists():
            continue  # Skip deleted or untracked

        # 1. Unowned Paths Check
        if classification in {"source", "test"} and owner is None:
            errors.append(f"ERROR: {path_str}: unowned {classification} file path")

        # 2. Python duplicate and import checks
        imported_modules = None
        repository_references = None
        if path_str.endswith(".py") and classification == "test":
            imported_modules = check_python_duplicates_and_imports(file_path, errors)
            repository_references = find_python_repository_references(file_path)
        elif path_str.endswith((".test.ts", ".test.tsx")) and classification == "test":
            repository_references = find_typescript_repository_references(file_path)
        elif path_str.endswith(".test.mjs") and classification == "test":
            repository_references = find_javascript_repository_references(file_path)

        # 3. Orphan Tests Check
        if classification == "test":
            if not matches_source(
                path_str,
                source_paths,
                allowed_orphans,
                imported_modules,
                workflow_paths,
                repository_references,
                reference_paths,
                contract_test_paths,
            ):
                errors.append(
                    f"ERROR: {path_str}: orphaned test file (no matching source file found)"
                )

            # 4. Duplicate Go test names check
            if path_str.endswith(".go"):
                check_go_duplicates(file_path, errors)

            # 5/6. Anti-Patterns Check
            check_anti_patterns(
                file_path, errors, allowed_sleeps, allowed_dynamic_skips
            )

    if errors:
        for violation in sorted(set(errors)):
            print(violation, file=sys.stderr)
        print(
            f"\nVerification FAILED. Found {len(set(errors))} violations.",
            file=sys.stderr,
        )
        return 1

    print("Quality inventory validation passed. All files and tests comply with rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
