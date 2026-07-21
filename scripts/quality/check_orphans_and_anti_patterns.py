from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

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
        self.scopes = [set()]  # Scope stack, index 0 is module scope
        self.imported_modules = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scopes.append(set())
        self.generic_visit(node)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("test_"):
            current_scope = self.scopes[-1]
            if node.name in current_scope:
                self.errors.append(
                    f"ERROR: {safe_relative_path(self.file_path)}: "
                    f"duplicate test function '{node.name}' in class/module context"
                )
            current_scope.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imported_modules.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imported_modules.add(node.module.split(".")[0])
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


def check_go_duplicates(file_path: Path, errors: list[str]) -> None:
    try:
        content = file_path.read_text(encoding="utf-8")
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
        ):
            return True

        base_name = name[5:]  # Remove 'test_'
        base_name_clean = base_name.replace(".py", "")
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

        # Check general endswith match
        for src in source_paths:
            if src.endswith(base_name_ts) or src.endswith(base_name_tsx):
                return True
        return False

    # 4. Go naming map
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
    except Exception as error:
        print(f"ERROR: failed to parse config/manifest: {error}", file=sys.stderr)
        return 2

    allowed_sleeps = mapping.get("allowed_sleeps", [])
    allowed_dynamic_skips = mapping.get("allowed_dynamic_skips", [])
    allowed_orphans = mapping.get("allowed_orphans", [])

    files = manifest.get("files", [])
    errors = []

    source_paths = {f["path"] for f in files if f["classification"] == "source"}

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
        if path_str.endswith(".py") and classification == "test":
            imported_modules = check_python_duplicates_and_imports(file_path, errors)

        # 3. Orphan Tests Check
        if classification == "test":
            if not matches_source(
                path_str, source_paths, allowed_orphans, imported_modules
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
        for error in sorted(set(errors)):
            print(error, file=sys.stderr)
        print(
            f"\nVerification FAILED. Found {len(set(errors))} violations.",
            file=sys.stderr,
        )
        return 1

    print("Quality inventory validation passed. All files and tests comply with rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
