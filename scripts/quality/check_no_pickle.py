"""AST guard for direct pickle and _pickle imports and API use."""

from __future__ import annotations

import argparse
import ast
import os
import stat
import sys
import tokenize
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

PICKLE_MODULES = frozenset({"pickle", "_pickle"})
PICKLE_API_NAMES = frozenset(
    {"load", "loads", "dump", "dumps", "Pickler", "Unpickler", "_Unpickler"}
)
DYNAMIC_IMPORT_APIS = frozenset({"builtins.__import__", "importlib.import_module"})
ALLOWED_PICKLE_FINDING_COUNT = 0


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str


class ScanError(RuntimeError):
    """Raised when source cannot be enumerated, read, or parsed completely."""


def _attribute_root(expression: ast.expr) -> str | None:
    while isinstance(expression, ast.Attribute):
        expression = expression.value
    if isinstance(expression, ast.Name):
        return expression.id
    return None


@dataclass(frozen=True)
class _StaticBinding:
    kind: str
    value: str


class _Scope:
    def __init__(
        self,
        parent: _Scope | None = None,
        *,
        local_names: Iterable[str] = (),
        kind: str = "module",
    ) -> None:
        self.parent = parent
        self.local_names = set(local_names)
        self.kind = kind
        self.values: dict[str, _StaticBinding | None] = {
            name: None for name in self.local_names
        }

    def lookup(self, name: str) -> _StaticBinding | None:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def is_bound(self, name: str) -> bool:
        return (
            name in self.values
            or name in self.local_names
            or (self.parent is not None and self.parent.is_bound(name))
        )

    def bind(self, name: str, value: _StaticBinding | None) -> None:
        self.local_names.add(name)
        self.values[name] = value

    def fork(self) -> _Scope:
        child = _Scope(self.parent, local_names=self.local_names, kind=self.kind)
        child.values = self.values.copy()
        return child


class _FunctionLocalNames(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        self._visit_definition_expressions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)
        self._visit_definition_expressions(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)
        for expression in (*node.decorator_list, *node.bases):
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expression in (*node.args.defaults, *node.args.kw_defaults):
            if expression is not None:
                self.visit(expression)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.names.add(node.name)
        if node.type is not None:
            self.visit(node.type)
        for statement in node.body:
            self.visit(statement)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name is not None:
            self.names.add(node.name)
        if node.pattern is not None:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.names.add(node.name)

    def _visit_definition_expressions(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for expression in node.decorator_list:
            self.visit(expression)
        for expression in (*node.args.defaults, *node.args.kw_defaults):
            if expression is not None:
                self.visit(expression)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if argument.annotation is not None:
                self.visit(argument.annotation)
        for argument in (node.args.vararg, node.args.kwarg):
            if argument is not None and argument.annotation is not None:
                self.visit(argument.annotation)
        if node.returns is not None:
            self.visit(node.returns)


class _NoPickleScanner:
    def __init__(self, filename: str) -> None:
        self.path = Path(filename)
        self.findings: list[Finding] = []

    def scan(self, tree: ast.Module) -> tuple[Finding, ...]:
        self._scan_block(tree.body, _Scope())
        return tuple(self.findings)

    def _record(self, node: ast.AST, message: str) -> None:
        self.findings.append(Finding(self.path, getattr(node, "lineno", 1), message))

    def _resolve_import(self, expression: ast.expr, scope: _Scope) -> str | None:
        if isinstance(expression, ast.Name):
            if expression.id == "__import__" and not scope.is_bound(expression.id):
                return "builtins.__import__"
            binding = scope.lookup(expression.id)
            if binding is not None and binding.kind == "import":
                return binding.value
            return None
        if isinstance(expression, ast.Attribute):
            parent = self._resolve_import(expression.value, scope)
            if parent is not None:
                return f"{parent}.{expression.attr}"
        return None

    def _resolve_string(self, expression: ast.expr, scope: _Scope) -> str | None:
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            return expression.value
        if isinstance(expression, ast.Name):
            binding = scope.lookup(expression.id)
            if binding is not None and binding.kind == "string":
                return binding.value
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
            left = self._resolve_string(expression.left, scope)
            right = self._resolve_string(expression.right, scope)
            if left is not None and right is not None:
                return left + right
        if isinstance(expression, ast.IfExp):
            body = self._resolve_string(expression.body, scope)
            alternative = self._resolve_string(expression.orelse, scope)
            if body == alternative:
                return body
        return None

    def _binding_for_expression(
        self, expression: ast.expr, scope: _Scope
    ) -> _StaticBinding | None:
        string_value = self._resolve_string(expression, scope)
        if string_value is not None:
            return _StaticBinding("string", string_value)
        import_value = self._resolve_import(expression, scope)
        if import_value is not None:
            return _StaticBinding("import", import_value)
        return None

    def _check_dynamic_call(self, call: ast.Call, scope: _Scope) -> None:
        importer = self._resolve_import(call.func, scope)
        if importer not in DYNAMIC_IMPORT_APIS:
            return
        module_expression = call.args[0] if call.args else None
        if module_expression is None:
            module_expression = next(
                (keyword.value for keyword in call.keywords if keyword.arg == "name"),
                None,
            )
        if module_expression is None:
            return
        module_name = self._resolve_string(module_expression, scope)
        if (
            module_name is not None
            and module_name.split(".", maxsplit=1)[0] in PICKLE_MODULES
        ):
            self._record(call, f"dynamic pickle import: {module_name}")

    def _check_pickle_api(self, node: ast.Attribute, scope: _Scope) -> None:
        if node.attr not in PICKLE_API_NAMES:
            return
        root = _attribute_root(node)
        import_value = self._resolve_import(node.value, scope)
        if import_value is not None:
            if import_value.split(".", maxsplit=1)[0] in PICKLE_MODULES:
                self._record(node, f"pickle API use: {node.attr}")
        elif root in PICKLE_MODULES and not scope.is_bound(root):
            self._record(node, f"pickle API use: {node.attr}")

    def _target_names(self, target: ast.expr) -> tuple[str, ...]:
        if isinstance(target, ast.Name):
            return (target.id,)
        if isinstance(target, (ast.Tuple, ast.List)):
            return tuple(
                name for item in target.elts for name in self._target_names(item)
            )
        if isinstance(target, ast.Starred):
            return self._target_names(target.value)
        return ()

    def _assign_target(
        self,
        target: ast.expr,
        value: _StaticBinding | None,
        scope: _Scope,
    ) -> None:
        if isinstance(target, ast.Name):
            scope.bind(target.id, value)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._assign_target(item, None, scope)
            return
        if isinstance(target, ast.Starred):
            self._assign_target(target.value, None, scope)

    def _scan_expression(self, expression: ast.expr, scope: _Scope) -> None:
        if isinstance(expression, ast.Call):
            self._check_dynamic_call(expression, scope)
            self._scan_expression(expression.func, scope)
            for argument in expression.args:
                self._scan_expression(argument, scope)
            for keyword in expression.keywords:
                self._scan_expression(keyword.value, scope)
            return
        if isinstance(expression, ast.Attribute):
            self._check_pickle_api(expression, scope)
            self._scan_expression(expression.value, scope)
            return
        if isinstance(expression, ast.NamedExpr):
            self._scan_expression(expression.value, scope)
            self._assign_target(
                expression.target,
                self._binding_for_expression(expression.value, scope),
                scope,
            )
            return
        if isinstance(expression, ast.Lambda):
            for value in (*expression.args.defaults, *expression.args.kw_defaults):
                if value is not None:
                    self._scan_expression(value, scope)
            child = _Scope(
                scope.fork(),
                local_names=self._argument_names(expression.args),
                kind="function",
            )
            self._scan_expression(expression.body, child)
            return
        if isinstance(
            expression, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            self._scan_comprehension(expression, scope)
            return
        for child in ast.iter_child_nodes(expression):
            if isinstance(child, ast.expr):
                self._scan_expression(child, scope)

    def _scan_comprehension(
        self,
        expression: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
        scope: _Scope,
    ) -> None:
        local_names = {
            name
            for generator in expression.generators
            for name in self._target_names(generator.target)
        }
        parent = scope.parent if scope.kind == "class" else scope
        child = _Scope(
            (parent or scope).fork(), local_names=local_names, kind="comprehension"
        )
        for index, generator in enumerate(expression.generators):
            iterator_scope = scope if index == 0 else child
            self._scan_expression(generator.iter, iterator_scope)
            self._assign_target(generator.target, None, child)
            for condition in generator.ifs:
                self._scan_expression(condition, child)
        if isinstance(expression, ast.DictComp):
            self._scan_expression(expression.key, child)
            self._scan_expression(expression.value, child)
        else:
            self._scan_expression(expression.elt, child)

    def _scan_block(
        self,
        statements: list[ast.stmt],
        scope: _Scope,
        *,
        defer_function_bodies: bool = False,
    ) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
        deferred: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for statement in statements:
            self._scan_statement(statement, scope, deferred)
        if not defer_function_bodies:
            for function in deferred:
                parent = scope.parent if scope.kind == "class" else scope
                self._scan_function(function, (parent or scope).fork())
        return deferred

    def _argument_names(self, arguments: ast.arguments) -> set[str]:
        names = {
            argument.arg
            for argument in (
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
            )
        }
        if arguments.vararg is not None:
            names.add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            names.add(arguments.kwarg.arg)
        return names

    def _scan_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent: _Scope,
    ) -> None:
        local_names = self._argument_names(node.args)
        collector = _FunctionLocalNames()
        for statement in node.body:
            collector.visit(statement)
        local_names.update(collector.names - collector.globals - collector.nonlocals)
        scope = _Scope(parent, local_names=local_names, kind="function")
        self._scan_block(node.body, scope)

    def _scan_definition_expressions(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: _Scope
    ) -> None:
        for expression in node.decorator_list:
            self._scan_expression(expression, scope)
        for expression in (*node.args.defaults, *node.args.kw_defaults):
            if expression is not None:
                self._scan_expression(expression, scope)
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if argument.annotation is not None:
                self._scan_expression(argument.annotation, scope)
        for argument in (node.args.vararg, node.args.kwarg):
            if argument is not None and argument.annotation is not None:
                self._scan_expression(argument.annotation, scope)
        if node.returns is not None:
            self._scan_expression(node.returns, scope)

    def _scan_statement(
        self,
        statement: ast.stmt,
        scope: _Scope,
        deferred: list[ast.FunctionDef | ast.AsyncFunctionDef],
    ) -> None:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root in PICKLE_MODULES:
                    self._record(statement, f"pickle module import: {alias.name}")
                bound = alias.asname or root
                imported = alias.name if alias.asname else root
                scope.bind(bound, _StaticBinding("import", imported))
            return
        if isinstance(statement, ast.ImportFrom):
            module = statement.module or ""
            root = module.split(".", maxsplit=1)[0]
            if statement.level == 0 and root in PICKLE_MODULES:
                self._record(statement, f"pickle symbol import: from {module}")
            for alias in statement.names:
                bound = alias.asname or alias.name
                imported = f"{module}.{alias.name}" if statement.level == 0 else None
                value = _StaticBinding("import", imported) if imported else None
                scope.bind(bound, value)
            return
        if isinstance(statement, ast.Assign):
            self._scan_expression(statement.value, scope)
            value = self._binding_for_expression(statement.value, scope)
            for target in statement.targets:
                self._assign_target(target, value, scope)
            return
        if isinstance(statement, ast.AnnAssign):
            self._scan_expression(statement.annotation, scope)
            if statement.value is not None:
                self._scan_expression(statement.value, scope)
            value = (
                self._binding_for_expression(statement.value, scope)
                if statement.value is not None
                else None
            )
            self._assign_target(statement.target, value, scope)
            return
        if isinstance(statement, ast.AugAssign):
            self._scan_expression(statement.target, scope)
            self._scan_expression(statement.value, scope)
            self._assign_target(statement.target, None, scope)
            return
        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                self._assign_target(target, None, scope)
            return
        if isinstance(statement, ast.Expr):
            self._scan_expression(statement.value, scope)
            return
        if isinstance(statement, ast.Return):
            if statement.value is not None:
                self._scan_expression(statement.value, scope)
            return
        if isinstance(statement, ast.Raise):
            if statement.exc is not None:
                self._scan_expression(statement.exc, scope)
            if statement.cause is not None:
                self._scan_expression(statement.cause, scope)
            return
        if isinstance(statement, ast.Assert):
            self._scan_expression(statement.test, scope)
            if statement.msg is not None:
                self._scan_expression(statement.msg, scope)
            return
        if isinstance(statement, ast.If):
            self._scan_expression(statement.test, scope)
            body = scope.fork()
            alternative = scope.fork()
            self._scan_block(statement.body, body)
            self._scan_block(statement.orelse, alternative)
            self._merge_scope(scope, (body, alternative))
            return
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._scan_expression(statement.iter, scope)
            entry = scope.fork()
            body = entry.fork()
            self._assign_target(statement.target, None, body)
            self._scan_block(statement.body, body)
            alternative = body.fork()
            self._scan_block(statement.orelse, alternative)
            self._merge_scope(scope, (entry, body, alternative))
            return
        if isinstance(statement, ast.While):
            self._scan_expression(statement.test, scope)
            entry = scope.fork()
            body = entry.fork()
            self._scan_block(statement.body, body)
            alternative = body.fork()
            self._scan_block(statement.orelse, alternative)
            self._merge_scope(scope, (entry, body, alternative))
            return
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                self._scan_expression(item.context_expr, scope)
                if item.optional_vars is not None:
                    self._assign_target(item.optional_vars, None, scope)
            self._scan_block(statement.body, scope)
            return
        if isinstance(statement, (ast.Try, ast.TryStar)):
            self._scan_try(statement, scope)
            return
        if isinstance(statement, ast.Match):
            self._scan_match(statement, scope)
            return
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._scan_definition_expressions(statement, scope)
            scope.bind(statement.name, None)
            deferred.append(statement)
            return
        if isinstance(statement, ast.ClassDef):
            for expression in (*statement.decorator_list, *statement.bases):
                self._scan_expression(expression, scope)
            for keyword in statement.keywords:
                self._scan_expression(keyword.value, scope)
            class_scope = _Scope(scope.fork(), kind="class")
            deferred = self._scan_block(
                statement.body, class_scope, defer_function_bodies=True
            )
            scope.bind(statement.name, None)
            for function in deferred:
                self._scan_function(function, scope.fork())
            return
        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.expr):
                self._scan_expression(child, scope)

    def _merge_scope(self, scope: _Scope, branches: Iterable[_Scope]) -> None:
        branch_list = tuple(branches)
        names = set(scope.values)
        for branch in branch_list:
            names.update(branch.values)
        for name in names:
            values = [branch.lookup(name) for branch in branch_list]
            first = values[0]
            scope.bind(name, first if all(value == first for value in values) else None)

    def _scan_try(self, statement: ast.Try | ast.TryStar, scope: _Scope) -> None:
        entry = scope.fork()
        body = entry.fork()
        self._scan_block(statement.body, body)
        normal = body.fork()
        self._scan_block(statement.orelse, normal)
        branches = [normal]
        for handler in statement.handlers:
            branch = entry.fork()
            if handler.type is not None:
                self._scan_expression(handler.type, branch)
            if handler.name is not None:
                branch.bind(handler.name, None)
            self._scan_block(handler.body, branch)
            branches.append(branch)
        self._merge_scope(scope, branches)
        self._scan_block(statement.finalbody, scope)

    def _scan_match(self, statement: ast.Match, scope: _Scope) -> None:
        self._scan_expression(statement.subject, scope)
        entry = scope.fork()
        branches = [entry]
        for case in statement.cases:
            branch = entry.fork()
            self._bind_pattern(case.pattern, branch)
            if case.guard is not None:
                self._scan_expression(case.guard, branch)
            self._scan_block(case.body, branch)
            branches.append(branch)
        self._merge_scope(scope, branches)

    def _bind_pattern(self, pattern: ast.pattern, scope: _Scope) -> None:
        if isinstance(pattern, ast.MatchAs):
            if pattern.name is not None:
                scope.bind(pattern.name, None)
            if pattern.pattern is not None:
                self._bind_pattern(pattern.pattern, scope)
        elif isinstance(pattern, ast.MatchStar):
            if pattern.name is not None:
                scope.bind(pattern.name, None)
        else:
            for child in ast.iter_child_nodes(pattern):
                if isinstance(child, ast.pattern):
                    self._bind_pattern(child, scope)


def scan_source(source: str, *, filename: str = "<memory>") -> tuple[Finding, ...]:
    """Find pickle imports and dynamic loads without reading comments."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        line = getattr(exc, "lineno", None) or 1
        message = getattr(exc, "msg", str(exc))
        raise ScanError(
            f"cannot parse Python source at {filename}:{line}: {message}"
        ) from exc
    return _NoPickleScanner(filename).scan(tree)


def _path_is_junction(path: Path) -> bool:
    try:
        return path.is_junction()
    except OSError as exc:
        raise ScanError(f"cannot inspect source path: {path}") from exc


def _walk_python_files(directory: Path) -> list[Path]:
    files: list[Path] = []

    def on_error(error: OSError) -> None:
        raise ScanError(
            f"cannot traverse source directory: {error.filename or directory}"
        ) from error

    try:
        for current, directory_names, file_names in os.walk(
            directory, followlinks=False, onerror=on_error
        ):
            current_path = Path(current)
            for directory_name in directory_names:
                child = current_path / directory_name
                if child.is_symlink():
                    raise ScanError(f"refusing source directory symlink: {child}")
                if _path_is_junction(child):
                    raise ScanError(f"refusing source directory junction: {child}")
            for file_name in file_names:
                child = current_path / file_name
                if Path(file_name).suffix.lower() != ".py":
                    continue
                if child.is_symlink():
                    raise ScanError(f"refusing source file symlink: {child}")
                files.append(child)
    except ScanError:
        raise
    except OSError as exc:
        raise ScanError(
            f"cannot traverse source directory: {exc.filename or directory}"
        ) from exc

    if not files:
        raise ScanError(f"no Python source files found in directory: {directory}")
    return files


def scan_paths(paths: Iterable[str | Path]) -> tuple[int, tuple[Finding, ...]]:
    inputs = [Path(path) for path in paths]
    if not inputs:
        raise ScanError("at least one scan path is required")

    python_files: dict[str, Path] = {}
    for path in inputs:
        if _path_is_junction(path):
            raise ScanError(f"refusing source path junction: {path}")
        try:
            info = path.lstat()
        except OSError as exc:
            raise ScanError(f"cannot inspect source path: {path}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ScanError(f"refusing source path symlink: {path}")
        if stat.S_ISREG(info.st_mode):
            if path.suffix.lower() != ".py":
                raise ScanError(f"scan file is not Python source: {path}")
            candidates = [path]
        elif stat.S_ISDIR(info.st_mode):
            candidates = _walk_python_files(path)
        else:
            raise ScanError(f"scan path is not a regular file or directory: {path}")

        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ScanError(f"cannot inspect source path: {candidate}") from exc
            python_files.setdefault(os.path.normcase(str(resolved)), resolved)

    findings: list[Finding] = []
    ordered_files = sorted(python_files.values(), key=lambda item: str(item))
    for path in ordered_files:
        try:
            with tokenize.open(path) as source_file:
                source = source_file.read()
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ScanError(f"cannot read Python source: {path}") from exc
        findings.extend(scan_source(source, filename=str(path)))
    return len(ordered_files), tuple(findings)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject pickle use in Python source.")
    parser.add_argument("paths", nargs="+", help="Python files or source directories")
    args = parser.parse_args(argv)
    try:
        file_count, findings = scan_paths(args.paths)
    except ScanError as exc:
        print(f"no_pickle_scan_error: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.message}")
    print(
        "no_pickle_scan "
        f"files={file_count} violations={len(findings)} "
        f"allowed={ALLOWED_PICKLE_FINDING_COUNT}"
    )
    return 1 if len(findings) > ALLOWED_PICKLE_FINDING_COUNT else 0


if __name__ == "__main__":
    raise SystemExit(main())
