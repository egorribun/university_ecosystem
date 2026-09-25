"""BE-04: the HTTP layer resolves services and sessions through Dishka only.

The legacy ``Depends(get_*_service)`` / ``Depends(get_db)`` factories opened
their own session per dependency.  On a route that also injected a service the
result was two sessions and two identity maps for one request, which is what
ADR-033 calls request-scoped session ownership and what SQLAlchemy reports as
"Object is already attached to session N".

These tests pin the boundary rather than the migration: a new route that
reaches for a legacy factory fails here instead of at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "app" / "api"

# ``app/api/deps`` is where the remaining legitimate dependencies are defined,
# so it is the one place allowed to name them.
DEPS_PACKAGE = API_ROOT / "deps"

# FastAPI security, locale and authorization dependencies stay on ``Depends``:
# they are request concerns, not services, and they already route their own
# database access through the container.
#
# The bare ``get_current_user`` / ``get_current_admin_user`` adapters are
# deliberately absent.  They open a FastAPI-owned session, which is the second
# identity map ADR-033 exists to prevent, and no route reaches for them any
# more -- the route ownership ledger reports zero approved_legacy routes.  They
# survive only as the implementation behind ``get_current_user_optional`` and
# as the name the test suite overrides, so a route naming one again is a
# regression this test must catch.
ALLOWED_DEPENDENCIES = frozenset(
    {
        "get_current_user_from_dishka",
        "get_current_user_optional_from_dishka",
        "get_current_user_dto",
        "get_current_user_auth_dto",
        "get_current_user_full",
        "get_current_admin_user_from_dishka",
        "get_permission_checker",
        "get_locale",
        "get_settings",
    }
)


def _api_modules() -> list[Path]:
    return sorted(
        path
        for path in API_ROOT.rglob("*.py")
        if DEPS_PACKAGE not in path.parents and path.parent != DEPS_PACKAGE
    )


def _depends_targets(path: Path) -> set[str]:
    """Every ``get_*`` name this module passes to ``Depends(...)``."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "Depends"):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
            continue
        name = node.args[0].id
        if name.startswith("get_"):
            found.add(name)
    return found


@pytest.mark.parametrize(
    "module", _api_modules(), ids=lambda path: path.relative_to(API_ROOT).as_posix()
)
def test_routes_do_not_depend_on_legacy_service_factories(
    module: Path,
) -> None:
    """No route may take a service or a session through ``Depends``."""

    offenders = sorted(_depends_targets(module) - ALLOWED_DEPENDENCIES)
    assert not offenders, (
        f"{module.relative_to(REPOSITORY_ROOT).as_posix()} injects "
        f"{offenders} through Depends; request-scoped services and sessions "
        "come from Dishka (FromDishka[T], or "
        "Annotated[T, FromComponent(READ_COMPONENT)] for the read replica)"
    )


def test_no_api_module_imports_a_legacy_session_dependency() -> None:
    """``get_db`` and ``get_read_db`` must not reach the HTTP layer at all.

    Importing them is the step before using them, and the import is what makes
    a second session available to a route in the first place.
    """

    offenders: list[str] = []
    for module in _api_modules():
        source = module.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            imported = {alias.name for alias in node.names}
            if imported & {"get_db", "get_read_db"}:
                offenders.append(module.relative_to(REPOSITORY_ROOT).as_posix())
                break

    assert not offenders, (
        f"{offenders} import a legacy session dependency; a route takes its "
        "session from Dishka so that authentication and the route body share "
        "one identity map"
    )


def test_every_injected_route_is_decorated_with_inject() -> None:
    """A ``FromDishka``/``FromComponent`` parameter is inert without ``@inject``.

    Without the decorator FastAPI treats the annotation as a request body and
    the route fails at call time rather than at import, so this catches the
    mistake at the boundary instead.
    """

    offenders: list[str] = []
    for module in _api_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            annotations = [
                ast.unparse(argument.annotation)
                for argument in node.args.args + node.args.kwonlyargs
                if argument.annotation is not None
            ]
            injects = any(
                "FromDishka" in text or "FromComponent" in text for text in annotations
            )
            if not injects:
                continue
            decorators = {ast.unparse(decorator) for decorator in node.decorator_list}
            if "inject" not in decorators:
                offenders.append(
                    f"{module.relative_to(REPOSITORY_ROOT).as_posix()}::{node.name}"
                )

    assert not offenders, f"these injected endpoints are missing @inject: {offenders}"
