#!/usr/bin/env python3
"""Fail closed on BE-04 FastAPI/Dishka route ownership drift.

The ledger is deliberately an AST inventory.  Importing the application would
run module initializers and make this architecture gate environment-dependent.
Legacy ownership is derived transitively from ``get_db``/``get_read_db``
through FastAPI ``Depends`` functions, so wrapper factories cannot hide a
second request-scoped database session.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROUTE_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace", "websocket"}
)
DISHKA_NON_SESSION_TYPES = frozenset(
    {
        "AuditService",
        "PermissionChecker",
        "RedisSessionService",
    }
)
LEGACY_SESSION_SEEDS = frozenset(
    {
        "app.core.database.get_db",
        "app.core.database.get_read_db",
    }
)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class _Function:
    symbol: str
    dependencies: frozenset[str]
    from_dishka_types: tuple[str, ...]
    has_inject: bool
    routes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Module:
    name: str
    aliases: dict[str, str]
    tree: ast.Module


def _module_name(app_root: Path, path: Path) -> str:
    relative = path.relative_to(app_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([app_root.name, *parts])


def _package_name(module: str, path: Path) -> str:
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _resolve_import_from(module: str, path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package_parts = _package_name(module, path).split(".")
    keep = len(package_parts) - (node.level - 1)
    base = package_parts[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _parse_modules(app_root: Path) -> dict[str, _Module]:
    modules: dict[str, _Module] = {}
    for path in sorted(app_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_name(app_root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                source = _resolve_import_from(module, path, node)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    aliases[alias.asname or alias.name] = f"{source}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    aliases[bound] = alias.name if alias.asname else bound
        modules[module] = _Module(name=module, aliases=aliases, tree=tree)
    return modules


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent is not None:
            return f"{parent}.{node.attr}"
    return None


def _resolve_reference(module: _Module, node: ast.AST) -> str | None:
    dotted = _dotted_name(node)
    if dotted is None:
        return None
    first, separator, rest = dotted.partition(".")
    if first in module.aliases:
        imported = module.aliases[first]
        return f"{imported}.{rest}" if separator else imported
    return f"{module.name}.{dotted}"


def _alias_targets(modules: dict[str, _Module]) -> dict[str, str]:
    targets: dict[str, str] = {}
    for module in modules.values():
        for local_name, target in module.aliases.items():
            targets[f"{module.name}.{local_name}"] = target
    return targets


def _canonical(symbol: str, aliases: dict[str, str]) -> str:
    seen: set[str] = set()
    while symbol in aliases and symbol not in seen:
        seen.add(symbol)
        symbol = aliases[symbol]
    return symbol


def _is_depends_call(module: _Module, call: ast.Call, aliases: dict[str, str]) -> bool:
    reference = _resolve_reference(module, call.func)
    if reference is None:
        return False
    return _canonical(reference, aliases) == "fastapi.Depends"


def _dependency_reference(
    module: _Module, call: ast.Call, aliases: dict[str, str]
) -> str | None:
    if not call.args:
        return None
    dependency: ast.AST = call.args[0]
    if isinstance(dependency, ast.Call):
        dependency = dependency.func
    reference = _resolve_reference(module, dependency)
    return _canonical(reference, aliases) if reference is not None else None


def _signature_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    nodes: list[ast.AST] = []
    arguments = [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]
    if function.args.vararg is not None:
        arguments.append(function.args.vararg)
    if function.args.kwarg is not None:
        arguments.append(function.args.kwarg)
    nodes.extend(argument.annotation for argument in arguments if argument.annotation)
    nodes.extend(function.args.defaults)
    nodes.extend(
        default for default in function.args.kw_defaults if default is not None
    )
    return nodes


def _from_dishka_types(
    module: _Module, nodes: list[ast.AST], aliases: dict[str, str]
) -> tuple[str, ...]:
    types: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if not isinstance(node, ast.Subscript):
                continue
            reference = _resolve_reference(module, node.value)
            if reference is not None and _canonical(reference, aliases).endswith(
                ".FromDishka"
            ):
                injected = _dotted_name(node.slice)
                types.add(injected or ast.unparse(node.slice))
    return tuple(sorted(types))


def _has_inject(
    module: _Module,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    aliases: dict[str, str],
) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        reference = _resolve_reference(module, target)
        if reference is not None and _canonical(reference, aliases).endswith(".inject"):
            return True
    return False


def _route_decorators(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[tuple[str, str], ...]:
    routes: list[tuple[str, str]] = []
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(
            decorator.func, ast.Attribute
        ):
            continue
        method = decorator.func.attr.lower()
        if method not in ROUTE_METHODS:
            continue
        if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
            raise ValueError(
                f"route {function.name} at line {function.lineno} must use a literal path"
            )
        path = decorator.args[0].value
        if not isinstance(path, str):
            raise ValueError(
                f"route {function.name} at line {function.lineno} must use a string path"
            )
        routes.append((method.upper(), path))
    return tuple(routes)


def _functions(modules: dict[str, _Module]) -> dict[str, _Function]:
    aliases = _alias_targets(modules)
    functions: dict[str, _Function] = {}
    for module in modules.values():
        for node in module.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            signature_nodes = _signature_nodes(node)
            dependency_nodes = [*signature_nodes, *node.decorator_list]
            dependencies: set[str] = set()
            for root in dependency_nodes:
                for candidate in ast.walk(root):
                    if not isinstance(candidate, ast.Call):
                        continue
                    if not _is_depends_call(module, candidate, aliases):
                        continue
                    dependency = _dependency_reference(module, candidate, aliases)
                    if dependency is not None:
                        dependencies.add(dependency)
            symbol = f"{module.name}.{node.name}"
            functions[symbol] = _Function(
                symbol=symbol,
                dependencies=frozenset(dependencies),
                from_dishka_types=_from_dishka_types(module, signature_nodes, aliases),
                has_inject=_has_inject(module, node, aliases),
                routes=_route_decorators(node),
            )
    return functions


def _ownership_closure(
    functions: dict[str, _Function], aliases: dict[str, str]
) -> tuple[set[str], set[str]]:
    legacy = set(LEGACY_SESSION_SEEDS)
    dishka = {
        symbol
        for symbol, function in functions.items()
        if any(
            injected_type.rsplit(".", 1)[-1] not in DISHKA_NON_SESSION_TYPES
            for injected_type in function.from_dishka_types
        )
    }
    changed = True
    while changed:
        changed = False
        for symbol, function in functions.items():
            dependencies = {
                _canonical(dependency, aliases) for dependency in function.dependencies
            }
            if symbol not in legacy and dependencies & legacy:
                legacy.add(symbol)
                changed = True
            if symbol not in dishka and dependencies & dishka:
                dishka.add(symbol)
                changed = True
    return legacy, dishka


def build_inventory(app_root: Path) -> dict[str, Any]:
    """Return the stable route ownership inventory for ``app_root``."""

    app_root = app_root.resolve()
    modules = _parse_modules(app_root)
    aliases = _alias_targets(modules)
    functions = _functions(modules)
    legacy_owners, dishka_owners = _ownership_closure(functions, aliases)
    routes: list[dict[str, Any]] = []

    for symbol, function in functions.items():
        if not function.routes:
            continue
        module_name, _, function_name = symbol.rpartition(".")
        direct_dependencies = {
            _canonical(dependency, aliases) for dependency in function.dependencies
        }
        legacy_dependencies = sorted(direct_dependencies & legacy_owners)
        dishka_dependencies = sorted(direct_dependencies & dishka_owners)
        has_legacy = symbol in legacy_owners
        has_dishka = symbol in dishka_owners
        signals = [
            *(f"FromDishka[{name}]" for name in function.from_dishka_types),
            *(["inject"] if function.has_inject else []),
        ]
        for method, path in function.routes:
            if has_legacy and has_dishka:
                ownership = "mixed"
            elif module_name.startswith("app.api.internal") or method == "WEBSOCKET":
                ownership = "worker_internal"
            elif has_dishka:
                ownership = "canonical_dishka"
            elif has_legacy:
                ownership = "approved_legacy"
            else:
                ownership = "public_no_db"
            routes.append(
                {
                    "id": f"{module_name}:{function_name}:{method}:{path}",
                    "ownership": ownership,
                    "legacy_dependencies": legacy_dependencies,
                    "dishka_dependencies": dishka_dependencies,
                    "dishka_signals": signals,
                }
            )

    routes.sort(key=lambda route: route["id"])
    summary: dict[str, int] = {}
    for route in routes:
        ownership = route["ownership"]
        summary[ownership] = summary.get(ownership, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "routes": routes,
        "summary": dict(sorted(summary.items())),
    }


def check_inventory(app_root: Path, ledger_path: Path) -> list[str]:
    """Compare current routes with the reviewed ledger and return violations."""

    try:
        current = build_inventory(app_root)
    except (OSError, SyntaxError, ValueError) as error:
        return [f"route dependency inventory scan failed: {error}"]

    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"route dependency inventory ledger is unavailable: {error}"]

    violations = [
        f"mixed route dependency ownership is forbidden: {route['id']}"
        for route in current["routes"]
        if route["ownership"] == "mixed"
    ]
    current_by_id = {route["id"]: route for route in current["routes"]}
    ledger_by_id = {route["id"]: route for route in ledger.get("routes", [])}

    for route_id in sorted(current_by_id.keys() - ledger_by_id.keys()):
        route = current_by_id[route_id]
        violations.append(
            f"route dependency inventory drift: added {route_id} ({route['ownership']})"
        )
    for route_id in sorted(ledger_by_id.keys() - current_by_id.keys()):
        route = ledger_by_id[route_id]
        violations.append(
            f"route dependency inventory drift: removed {route_id} ({route['ownership']})"
        )
    for route_id in sorted(current_by_id.keys() & ledger_by_id.keys()):
        if current_by_id[route_id] != ledger_by_id[route_id]:
            violations.append(f"route dependency inventory drift: changed {route_id}")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        violations.append(
            "route dependency inventory schema mismatch: "
            f"expected {SCHEMA_VERSION}, got {ledger.get('schema_version')!r}"
        )
    return violations


def _write_inventory(app_root: Path, ledger_path: Path) -> None:
    ledger_path.write_text(
        json.dumps(build_inventory(app_root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, default=Path("app"))
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("quality/route-dependency-inventory.json"),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the ledger with the current reviewed inventory",
    )
    args = parser.parse_args()
    if args.write:
        _write_inventory(args.app_root, args.ledger)
        print(f"wrote route dependency inventory: {args.ledger}")
        return 0

    violations = check_inventory(args.app_root, args.ledger)
    if violations:
        print("BE-04 route dependency inventory failed:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("BE-04 route dependency inventory is current; mixed ownership: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
