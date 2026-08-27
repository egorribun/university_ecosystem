"""Plan and exercise Alembic downgrades without crossing data-loss barriers."""

from __future__ import annotations

import argparse
import ast
import re
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATIONS_DIR = REPOSITORY_ROOT / "alembic" / "versions"
_REVISION_ID = re.compile(r"^[A-Za-z0-9_]+$")


class PolicyError(RuntimeError):
    """Raised when migration downgrade policy is incomplete or ambiguous."""


class MigrationMetadata(NamedTuple):
    revision: str
    parents: tuple[str, ...]
    path: Path
    irreversible_reason: str | None


class DowngradePlan(NamedTuple):
    head_revision: str
    safe_target: str
    boundary_revision: str | None
    boundary_parent: str | None
    boundary_reason: str | None


def _assignment_value(tree: ast.Module, name: str) -> object | None:
    matches: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                matches.append(node.value)
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                matches.append(node.value)
    if len(matches) > 1:
        raise PolicyError(f"migration declares {name!r} more than once")
    if not matches:
        return None
    try:
        return ast.literal_eval(matches[0])
    except (TypeError, ValueError) as error:
        raise PolicyError(f"migration {name!r} must be a literal") from error


def _downgrade_function(tree: ast.Module, path: Path) -> ast.FunctionDef:
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    ]
    if len(functions) != 1:
        raise PolicyError(f"{path.name}: must define exactly one downgrade() function")
    return functions[0]


def _declared_raise_reason(function: ast.FunctionDef) -> tuple[str | None, bool]:
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body = body[1:]
    has_raise = any(isinstance(node, ast.Raise) for node in ast.walk(function))
    if len(body) != 1 or not isinstance(body[0], ast.Raise):
        return None, has_raise
    exception = body[0].exc
    if not (
        isinstance(exception, ast.Call)
        and isinstance(exception.func, ast.Name)
        and exception.func.id == "RuntimeError"
        and len(exception.args) == 1
        and not exception.keywords
    ):
        return None, has_raise
    argument = exception.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value, has_raise
    if isinstance(argument, ast.Name) and argument.id == "downgrade_reason":
        return "<declared-name>", has_raise
    return None, has_raise


def _parse_migration(path: Path) -> MigrationMetadata:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        raise PolicyError(f"cannot parse migration {path.name}: {error}") from error

    revision = _assignment_value(tree, "revision")
    if not isinstance(revision, str) or not _REVISION_ID.fullmatch(revision):
        raise PolicyError(f"{path.name}: revision must be a safe non-empty literal")
    raw_parents = _assignment_value(tree, "down_revision")
    if raw_parents is None:
        parents: tuple[str, ...] = ()
    elif isinstance(raw_parents, str):
        parents = (raw_parents,)
    elif (
        isinstance(raw_parents, tuple)
        and raw_parents
        and all(isinstance(parent, str) for parent in raw_parents)
    ):
        parents = raw_parents
    else:
        raise PolicyError(f"{path.name}: down_revision must be a literal revision set")
    if any(not _REVISION_ID.fullmatch(parent) for parent in parents):
        raise PolicyError(f"{path.name}: down_revision contains an unsafe revision id")

    policy = _assignment_value(tree, "downgrade_policy")
    reason = _assignment_value(tree, "downgrade_reason")
    downgrade = _downgrade_function(tree, path)
    raised_reason, has_raise = _declared_raise_reason(downgrade)

    if policy is None:
        if reason is not None:
            raise PolicyError(
                f"{path.name}: downgrade_reason requires a downgrade policy"
            )
        if has_raise:
            raise PolicyError(
                f"{path.name}: downgrade raises without an irreversible policy"
            )
        return MigrationMetadata(revision, parents, path, None)
    if policy != "irreversible":
        raise PolicyError(f"{path.name}: unsupported downgrade policy {policy!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise PolicyError(
            f"{path.name}: irreversible downgrade needs a non-empty reason"
        )
    if len(parents) > 1:
        raise PolicyError(f"{path.name}: irreversible merge boundaries are ambiguous")
    if raised_reason is None:
        raise PolicyError(
            f"{path.name}: irreversible downgrade must fail before changing schema"
        )
    if raised_reason not in {reason, "<declared-name>"}:
        raise PolicyError(f"{path.name}: downgrade does not raise the declared reason")
    return MigrationMetadata(revision, parents, path, reason)


def build_downgrade_plan(migrations_dir: Path) -> DowngradePlan:
    """Return the newest declared data-loss boundary reachable from the head."""
    paths = sorted(migrations_dir.glob("*.py"))
    if not paths:
        raise PolicyError(f"no Alembic migrations found in {migrations_dir}")
    migrations: dict[str, MigrationMetadata] = {}
    for path in paths:
        migration = _parse_migration(path)
        if migration.revision in migrations:
            raise PolicyError(f"duplicate migration revision {migration.revision!r}")
        migrations[migration.revision] = migration

    referenced = {
        parent for migration in migrations.values() for parent in migration.parents
    }
    missing = sorted(referenced - migrations.keys())
    if missing:
        raise PolicyError(f"migration graph references missing revisions: {missing!r}")
    heads = sorted(migrations.keys() - referenced)
    if len(heads) != 1:
        raise PolicyError(f"expected exactly one migration head, found {heads!r}")

    head = heads[0]
    distances: dict[str, int] = {head: 0}
    queue: deque[str] = deque([head])
    while queue:
        revision = queue.popleft()
        for parent in migrations[revision].parents:
            distance = distances[revision] + 1
            if parent not in distances or distance < distances[parent]:
                distances[parent] = distance
                queue.append(parent)
    unreachable = sorted(migrations.keys() - distances.keys())
    if unreachable:
        raise PolicyError(
            f"migration graph has revisions unreachable from head: {unreachable!r}"
        )

    boundaries = [
        migration
        for migration in migrations.values()
        if migration.irreversible_reason is not None
    ]
    if not boundaries:
        return DowngradePlan(head, "base", None, None, None)
    nearest_distance = min(distances[migration.revision] for migration in boundaries)
    nearest = [
        migration
        for migration in boundaries
        if distances[migration.revision] == nearest_distance
    ]
    if len(nearest) != 1:
        revisions = sorted(migration.revision for migration in nearest)
        raise PolicyError(
            f"multiple latest irreversible boundaries are ambiguous: {revisions!r}"
        )
    boundary = nearest[0]
    parent = boundary.parents[0] if boundary.parents else "base"
    return DowngradePlan(
        head,
        boundary.revision,
        boundary.revision,
        parent,
        boundary.irreversible_reason,
    )


def assert_declared_boundary(
    plan: DowngradePlan,
    downgrade: Callable[[str], None],
) -> None:
    """Prove that the declared barrier blocks with its exact audited reason."""
    if plan.boundary_revision is None:
        return
    if plan.boundary_parent is None or plan.boundary_reason is None:
        raise PolicyError("irreversible boundary plan is incomplete")
    try:
        downgrade(plan.boundary_parent)
    except RuntimeError as error:
        if str(error) != plan.boundary_reason:
            raise PolicyError(
                f"irreversible boundary raised an unexpected error: {error}"
            ) from error
    else:
        raise PolicyError(
            f"irreversible boundary {plan.boundary_revision!r} allowed the downgrade"
        )


def _write_github_outputs(plan: DowngradePlan) -> None:
    print(f"safe_target={plan.safe_target}")
    print(f"boundary_revision={plan.boundary_revision or 'none'}")
    print(f"boundary_parent={plan.boundary_parent or 'none'}")


def _assert_runtime_boundary(plan: DowngradePlan, config_path: Path) -> None:
    from alembic.config import Config

    from alembic import command

    config = Config(str(config_path))
    assert_declared_boundary(plan, lambda target: command.downgrade(config, target))
    if plan.boundary_revision is not None:
        print(
            "Validated irreversible migration boundary "
            f"{plan.boundary_revision}: {plan.boundary_reason}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("plan", "assert-boundary"),
        help="emit a safe target or exercise the declared runtime barrier",
    )
    parser.add_argument("--migrations-dir", type=Path, default=DEFAULT_MIGRATIONS_DIR)
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / "alembic.ini")
    args = parser.parse_args(argv)

    try:
        plan = build_downgrade_plan(args.migrations_dir)
        if args.command == "plan":
            _write_github_outputs(plan)
        else:
            _assert_runtime_boundary(plan, args.config)
    except PolicyError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
