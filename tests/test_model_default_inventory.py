"""Fail-closed contracts for the SQLAlchemy model-default inventory."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.quality.audit_model_defaults import (
    InventoryError,
    build_inventory,
    check_inventory,
    read_migration_head,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "quality" / "model-default-policy.json"
_GIT = shutil.which("git") or "git"


def _current_sha() -> str:
    return subprocess.run(  # noqa: S603 - fixed local git command
        [_GIT, "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_repository_inventory_is_current_and_owner_scoped() -> None:
    inventory = cast(
        dict[str, Any], build_inventory(REPO_ROOT, policy_path=POLICY_PATH)
    )

    assert inventory["source"]["git_sha"] == _current_sha()
    assert inventory["source"]["migration_head"] == "202608270003"
    assert inventory["summary"] == {
        "computed_columns": ["events.search_vector"],
        "effective_counts": {"both": 26, "python_only": 91, "server_only": 17},
        "effective_default_count": 134,
        "source_counts": {"both": 26, "python_only": 65, "server_only": 17},
        "source_default_none_count": 10,
        "source_mapped_column_count": 108,
        "table_count": 45,
    }

    columns = {item["column"]: item for item in inventory["columns"]}
    assert columns["active_sessions.signing_key"]["exception_owner"] == "backend-auth"
    assert columns["groups.id"]["exception_kind"] == "inherited_uuid7_primary_key"
    assert columns["events.search_vector"]["classification"] == "computed"
    assert all(
        item["exception_owner"] is not None
        for item in inventory["columns"]
        if item["exception_kind"] is not None
    )


def test_inventory_check_accepts_current_complete_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "model-default-inventory.json"
    artifact.write_text(
        json.dumps(build_inventory(REPO_ROOT, policy_path=POLICY_PATH), sort_keys=True),
        encoding="utf-8",
    )

    assert (
        check_inventory(
            artifact,
            repo_root=REPO_ROOT,
            policy_path=POLICY_PATH,
        )
        == []
    )


def test_inventory_check_rejects_old_sha_and_partial_payload(tmp_path: Path) -> None:
    artifact = tmp_path / "model-default-inventory.json"
    payload = cast(dict[str, Any], build_inventory(REPO_ROOT, policy_path=POLICY_PATH))
    payload["source"]["git_sha"] = "0" * 40
    payload["columns"] = payload["columns"][:-1]
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    errors = check_inventory(
        artifact,
        repo_root=REPO_ROOT,
        policy_path=POLICY_PATH,
    )

    assert any("git_sha" in error for error in errors)
    assert any("payload drift" in error for error in errors)


def test_policy_rejects_unknown_exception_without_postgres(tmp_path: Path) -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["exceptions"].append(
        {
            "column": "users.unknown_column",
            "kind": "application_secret",
            "owner": "security",
            "reason": "fixture must fail closed",
        }
    )
    policy["exceptions"].sort(key=lambda item: item["column"])
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(InventoryError, match="unknown column"):
        build_inventory(REPO_ROOT, policy_path=policy_path)


def test_migration_head_parser_supports_merge_tuples_and_rejects_dynamic_values(
    tmp_path: Path,
) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "base.py").write_text(
        'revision = "base"\ndown_revision = None\n',
        encoding="utf-8",
    )
    (versions / "left.py").write_text(
        'revision = "left"\ndown_revision = "base"\n',
        encoding="utf-8",
    )
    (versions / "right.py").write_text(
        'revision = "right"\ndown_revision = "base"\n',
        encoding="utf-8",
    )
    (versions / "merge.py").write_text(
        'revision = "merge"\ndown_revision = ("left", "right")\n',
        encoding="utf-8",
    )
    assert read_migration_head(versions) == "merge"

    (versions / "bad.py").write_text(
        'revision = "bad"\ndown_revision = os.environ["REV"]\n',
        encoding="utf-8",
    )
    with pytest.raises(InventoryError, match="literal"):
        read_migration_head(versions)
