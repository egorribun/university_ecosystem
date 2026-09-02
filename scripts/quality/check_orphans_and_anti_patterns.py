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
        for default in arguments.kw_defaults:
            if default is not None:
                self.visit(default)

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
    workflow_paths: set[str] | None = None,
    repository_references: set[str] | None = None,
    reference_paths: set[str] | None = None,
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
            or "scripts" in imported_modules
        ):
            return True

        # Contract tests often validate authored repository assets that are not
        # executable runtime source: migrations, Helm charts, hooks, schemas,
        # or quality scripts. Accept only AST-resolved Path expressions that
        # point to a real non-test inventory target.
        if repository_references and _references_inventory_target(
            repository_references, reference_paths or set()
        ):
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
    reference_paths = {f["path"] for f in files if f["classification"] != "test"}
    # Workflows are classified as utilities. Keep them separate from ordinary
    # source paths so only the exact workflow-contract matcher may use them.
    workflow_paths = {
        f["path"]
        for f in files
        if f["path"].startswith(".github/workflows/")
        and f["path"].endswith((".yml", ".yaml"))
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
