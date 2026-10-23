from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# Issue patterns in comments (e.g. QUALITY-123, TD-456, FIX-789, RZ-10-02)
ISSUE_PATTERN = re.compile(
    r"\b(QUALITY|TD|FIX|RZ|MOD|DESIGN|CQ|INFRA|A11Y)-\d+(\w+)?\b", re.IGNORECASE
)

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

# Dynamic skip patterns
SKIP_PATTERNS = [
    (re.compile(r"\bpytest\.skip\("), "Python dynamic skip (pytest.skip) found"),
    (re.compile(r"\bt\.Skip\("), "Go dynamic skip (t.Skip) found"),
    (re.compile(r"\btest\.skip\("), "JS/TS dynamic skip (test.skip) found"),
    (re.compile(r"\bit\.skip\("), "JS/TS dynamic skip (it.skip) found"),
]

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


def _mask_javascript_non_code(content: str) -> tuple[str, dict[str, str]]:
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
        if node.module:
            self.imported_modules.add(node.module)
            self.imported_modules.add(node.module.split(".")[0])
            for alias in node.names:
                if alias.name != "*":
                    self.imported_modules.add(f"{node.module}.{alias.name}")
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


_REPOSITORY_ROOT_NAMES = frozenset({"ROOT", "REPOSITORY_ROOT", "PROJECT_ROOT"})


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
            resolved = _static_repository_path_parts(node, active_root_names, file_path)
            if resolved is not None and resolved[0]:
                references.add("/".join(resolved[0]))
        for name, binding_statement in authoritative_statements.items():
            if binding_statement is statement:
                active_root_names.add(name)
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

    references: set[str] = set()
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


def check_anti_patterns(
    file_path: Path,
    errors: list[str],
    allowed_sleeps: list[str],
    allowed_dynamic_skips: list[str],
) -> None:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
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

        # 3. Dynamic skips
        if not is_skip_allowed:
            for regex, msg in SKIP_PATTERNS:
                if regex.search(line):
                    # Search for tracking issue and owner
                    has_issue = ISSUE_PATTERN.search(line) is not None
                    has_owner = "@" in line

                    # Check preceding line as well
                    if line_idx > 1:
                        prev_line = lines[line_idx - 2]
                        if ISSUE_PATTERN.search(prev_line):
                            has_issue = True
                        if "@" in prev_line:
                            has_owner = True

                    if not (has_issue and has_owner) and "quarantined" not in line:
                        errors.append(
                            f"ERROR: {path_str}:L{line_idx}: {msg} requires tracking issue (e.g. QUALITY-123) and owner (@username) in comment"
                        )


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
    if matches_any_glob(test_path, allowed_orphans):
        return True

    # 1. Allowed non-orphan folders
    allowed_folders = {
        "tests/integration",
        "tests/chaos",
        "tests/contracts",
        "tests/performance",
        "tests/fuzz",
    }
    for folder in allowed_folders:
        if test_path.startswith(folder + "/"):
            return True

    # Static repository-file reads are direct contract dependencies across
    # languages. Accept them only when their resolved target exists in the
    # inventory as a non-test path.
    generic_reference_paths = reference_paths or set()
    if test_path.endswith(".test.mjs"):
        # A Playwright spec is a test-to-test contract target only for the exact
        # contract matcher below; its utility inventory classification must not
        # make every MJS test referencing it appear covered.
        generic_reference_paths = generic_reference_paths - (
            contract_test_paths or set()
        )
    if repository_references and _references_inventory_target(
        repository_references, generic_reference_paths
    ):
        return True

    # A JavaScript contract test may assert against one exact Playwright spec it
    # statically reads. Keep this test-to-test relationship limited to files
    # explicitly named as contract tests and exact existing .spec.ts[x] targets.
    if (
        test_path.endswith(".test.mjs")
        and re.search(r"(?:^|[.-])contract\.test\.mjs$", Path(test_path).name)
        and repository_references
        and repository_references.intersection(contract_test_paths or set())
    ):
        return True

    # Remove test/test_ prefix/suffix
    path_obj = Path(test_path)
    name = path_obj.name

    # 2. Python import & naming map
    if (
        test_path.startswith("tests/")
        and name.startswith("test_")
        and test_path.endswith(".py")
    ):
        if imported_modules and (
            "app" in imported_modules
            or "services" in imported_modules
            or "native" in imported_modules
            or "scripts" in imported_modules
        ):
            return True

        # Test support modules are authored repository utilities rather than
        # production source.  Treat an import of one as a concrete ownership
        # relationship only when its fully-qualified module resolves to a
        # non-test inventory path; importing another test file must not bypass
        # the orphan gate.
        if imported_modules and reference_paths:
            for module in imported_modules:
                if not module.startswith("tests."):
                    continue
                module_path = module.replace(".", "/") + ".py"
                if module_path in reference_paths:
                    return True

        base_name = name[5:]  # Remove 'test_'
        base_name_clean = base_name.replace(".py", "")

        # Workflow-contract suites intentionally verify a workflow document
        # rather than importing executable Python.  Map the conventional
        # ``test_<workflow>_workflow_contract.py`` name to that document so a
        # new contract test remains governed by the orphan gate.
        workflow_name = base_name_clean.removesuffix("_workflow_contract")
        if workflow_name != base_name_clean and any(
            Path(workflow_path).parent == Path(".github/workflows")
            and Path(workflow_path).suffix in {".yml", ".yaml"}
            and Path(workflow_path).stem.replace("-", "_") == workflow_name
            for workflow_path in workflow_paths or set()
        ):
            return True

        # Remove common suffixes
        for suffix in ("_service", "_api", "_full", "_coverage", "_unit", "_booster"):
            if base_name_clean.endswith(suffix):
                base_name_clean = base_name_clean[: -len(suffix)]

        # Check matching folders or general name match
        for src in source_paths:
            src_name = Path(src).name
            if src.endswith(base_name) or src.endswith(
                base_name.replace(".py", "/__init__.py")
            ):
                return True
            if base_name_clean in src_name:
                return True
        return False

    # 3. TS/JS naming map
    if test_path.endswith((".test.ts", ".test.tsx")):
        # If it imports from local source, we consider it matched
        try:
            content = Path(test_path).read_text(encoding="utf-8")
            if re.search(r'from\s+[\'"](@/|\.|\.\.)', content) or re.search(
                r'import\s+[\'"](@/|\.|\.\.)', content
            ):
                return True
        except Exception:  # noqa: S110
            pass

        base_name_ts = name.replace(".test.ts", ".ts").replace(".test.tsx", ".ts")
        base_name_tsx = name.replace(".test.ts", ".tsx").replace(".test.tsx", ".tsx")
        # Coverage-closure suites use a descriptive segment before the test
        # suffix (for example ``rateLimit.closure.test.ts``). Normalize that
        # segment before matching the test against its production module.
        base_name_ts = re.sub(
            r"\.(?:branches|booster|closure|edge)(?=\.tsx?$)", "", base_name_ts
        )
        base_name_tsx = re.sub(
            r"\.(?:branches|booster|closure|edge)(?=\.tsx?$)", "", base_name_tsx
        )

        # Check local folder
        local_src_ts = str(path_obj.parent / base_name_ts).replace("\\", "/")
        local_src_tsx = str(path_obj.parent / base_name_tsx).replace("\\", "/")
        if local_src_ts in source_paths or local_src_tsx in source_paths:
            return True

        # Check __tests__ parent
        if "/__tests__/" in test_path:
            parent_src_ts = (
                test_path.replace("/__tests__/", "/")
                .replace(".test.ts", ".ts")
                .replace(".test.tsx", ".ts")
            )
            parent_src_tsx = (
                test_path.replace("/__tests__/", "/")
                .replace(".test.ts", ".tsx")
                .replace(".test.tsx", ".tsx")
            )
            if parent_src_ts in source_paths or parent_src_tsx in source_paths:
                return True

        # Production/runtime suites may add one or more descriptive segments
        # before `.test.ts[x]` (for example `client.csrf.production.test.ts`).
        # Match those suites to a nearby source module by a dot-delimited stem;
        # requiring the source directory to be the test directory or its
        # `__tests__` parent avoids matching unrelated modules with a common
        # prefix.
        test_stem = name.rsplit(".test.", 1)[0]
        nearby_source_dirs = {path_obj.parent}
        if path_obj.parent.name == "__tests__":
            nearby_source_dirs.add(path_obj.parent.parent)
        for src in source_paths:
            src_path = Path(src)
            if src_path.parent not in nearby_source_dirs:
                continue
            source_stem = src_path.stem
            if test_stem == source_stem or test_stem.startswith(source_stem + "."):
                return True

        # Check general endswith match
        for src in source_paths:
            if src.endswith(base_name_ts) or src.endswith(base_name_tsx):
                return True
        return False

    # 4. JavaScript module tests require a statically referenced inventoried
    # non-test file or an exact nearby module with the same test stem.
    if test_path.endswith(".test.mjs"):
        test_stem = name.removesuffix(".test.mjs")
        nearby_source_dirs = {path_obj.parent, path_obj.parent.parent}
        for source in source_paths:
            source_path = Path(source)
            if (
                source_path.parent in nearby_source_dirs
                and source_path.suffix in {".mjs", ".js", ".cjs"}
                and source_path.stem == test_stem
            ):
                return True
        return False

    # 5. Go naming map
    if test_path.endswith("_test.go"):
        base_name = name.replace("_test.go", ".go")
        local_src = str(path_obj.parent / base_name).replace("\\", "/")
        if local_src in source_paths:
            return True
        # If any other .go file is in the same directory, it is matching
        dir_path = path_obj.parent
        for src in source_paths:
            if Path(src).parent == dir_path:
                return True
        return False

    return True


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
