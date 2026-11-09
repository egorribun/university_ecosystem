from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _checker_source() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name")
        == "MOD-30-01: Enforce lazy=noload on SQLAlchemy relationships"
    )
    run = step["run"]
    marker = "python3 - <<'PY'\n"
    assert marker in run and run.endswith("PY\n"), (
        "MOD-30-01 must use the tested Python gate"
    )
    return run.split(marker, 1)[1].rsplit("\nPY", 1)[0]


CHECKER = _checker_source()


def _run_gate(tmp_path: Path, source: str, *, expect_ok: bool) -> None:
    model = tmp_path / "app" / "models" / "fixture.py"
    model.parent.mkdir(parents=True)
    model.write_text(source, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter running repository-owned gate source
        [sys.executable, "-c", CHECKER],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) is expect_ok, (
        f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_literal_noload_is_accepted(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("User", lazy="noload")\n',
        expect_ok=True,
    )


@pytest.mark.parametrize(
    "declaration",
    [
        'relationship("User")',
        'relationship("User", lazy="joined")',
    ],
    ids=["missing", "non-noload"],
)
def test_missing_or_non_noload_lazy_is_rejected(
    tmp_path: Path, declaration: str
) -> None:
    _run_gate(
        tmp_path,
        f"from sqlalchemy.orm import relationship\n{declaration}\n",
        expect_ok=False,
    )


def test_single_call_exemption_is_accepted(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("User", lazy="joined")  # noload-exempt: required eager read\n',
        expect_ok=True,
    )


def test_inline_lazy_argument_exemption_is_accepted(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("User",\n    lazy="joined",  # noload-exempt: fixed eager read\n)\n',
        expect_ok=True,
    )


def test_empty_exemption_reason_is_rejected(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("User", lazy="joined")  # noload-exempt:\n',
        expect_ok=False,
    )


def test_unique_exemption_does_not_hide_another_relationship(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("A", lazy="noload")\nrelationship("B", lazy="joined")  # noload-exempt: only B\n',
        expect_ok=True,
    )


def test_one_exemption_cannot_cover_two_relationships_on_one_line(
    tmp_path: Path,
) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("A", lazy="joined"); relationship("B", lazy="joined")  # noload-exempt: only B\n',
        expect_ok=False,
    )


@pytest.mark.parametrize(
    "source",
    [
        'from sqlalchemy.orm import relationship\nrel = relationship\nrel("User", lazy="joined")\n',
        'import sqlalchemy.orm\nrel = sqlalchemy.orm.relationship\nrel("User", lazy="joined")\n',
        'from sqlalchemy.orm import relationship\nrel = relationship\nalias = rel\nalias("User", lazy="joined")\n',
        'from sqlalchemy.orm import relationship\nrel = relationship if choose_alias else helper\nrel("User", lazy="joined")\n',
    ],
    ids=["direct", "qualified", "multi-hop", "conditional"],
)
def test_static_relationship_aliases_are_checked(tmp_path: Path, source: str) -> None:
    _run_gate(tmp_path, source, expect_ok=False)


def test_ordinary_helper_alias_is_not_mistaken_for_relationship(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from helpers import factory\nalias = factory\nalias("ordinary helper")\n',
        expect_ok=True,
    )


def test_comment_and_string_text_are_not_relationship_calls(tmp_path: Path) -> None:
    source = """# relationship("User", lazy="joined")
example = "relationship('User', lazy='joined')"
"""
    _run_gate(tmp_path, source, expect_ok=True)


def test_string_cannot_impersonate_exemption(tmp_path: Path) -> None:
    _run_gate(
        tmp_path,
        'from sqlalchemy.orm import relationship\nrelationship("User", info={"note": "# noload-exempt: fake"})\n',
        expect_ok=False,
    )
