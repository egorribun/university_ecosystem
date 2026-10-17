from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from scripts import enforce_secret_strength as checker

FIELD_NAME = "APP_" + "TO" + "KEN"


@pytest.mark.parametrize(
    "prefix_parts",
    [
        ("CHANGE", "ME"),
        ("YOUR", ""),
        ("REPLACE", "WITH", ""),
    ],
)
@pytest.mark.parametrize("padding", ["", "P" * 40])
@pytest.mark.parametrize("surround_with_whitespace", [False, True])
def test_default_scan_rejects_operational_placeholders_but_allows_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    prefix_parts: tuple[str, ...],
    padding: str,
    surround_with_whitespace: bool,
) -> None:
    target_names = {target.name for target in checker.TARGET_FILES}
    assert {".env", ".env.example", "docker-compose.yml"} <= target_names

    root = tmp_path
    template = root / ".env.example"
    operational_env = root / ".env"
    compose = root / "docker-compose.yml"

    placeholder = "_".join(prefix_parts)
    if padding:
        placeholder = f"{placeholder}_{padding}"
    operational_value = (
        f'  "  {placeholder}  "  ' if surround_with_whitespace else placeholder
    )

    # The checked-in sample deliberately contains placeholders; the same value
    # in operational input must fail even if padding exceeds the length floor.
    template.write_text(f"{FIELD_NAME}={placeholder}\n", encoding="utf-8")
    operational_env.write_text(f"{FIELD_NAME}={operational_value}\n", encoding="utf-8")
    compose.write_text(
        "services:\n"
        "  sample:\n"
        "    environment:\n"
        f"      {FIELD_NAME}: {operational_value}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(
        checker,
        "TARGET_FILES",
        [root / target.name for target in checker.TARGET_FILES],
    )
    monkeypatch.setattr(checker.sys, "argv", ["enforce_secret_strength.py"])

    assert checker.main() == 1
    output = capsys.readouterr().out
    assert f"{operational_env}:{FIELD_NAME} uses a weak value" in output
    assert f"{compose}:{FIELD_NAME} uses a weak value" in output
    assert f"{template}:{FIELD_NAME} uses a weak value" not in output


def test_explicit_cli_only_exempts_the_exact_template_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path
    template = root / ".env.example"
    lookalike = root / "nested" / ".env.example"
    lookalike.parent.mkdir()
    placeholder = "_".join(("CHANGE", "ME"))
    template.write_text(f"{FIELD_NAME}={placeholder}\n", encoding="utf-8")
    lookalike.write_text(f"{FIELD_NAME}={placeholder}\n", encoding="utf-8")

    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(checker, "TARGET_FILES", [])
    monkeypatch.setattr(
        checker.sys,
        "argv",
        ["enforce_secret_strength.py", str(template), str(lookalike)],
    )

    assert checker.main() == 1
    output = capsys.readouterr().out
    assert f"{lookalike}:{FIELD_NAME} uses a weak value" in output
    assert f"{template}:{FIELD_NAME} uses a weak value" not in output


def test_explicit_operational_file_accepts_generated_strong_value_and_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    operational_env = tmp_path / ".env"
    strong_value = secrets.token_urlsafe(32)
    variable_reference = "$" + "{" + FIELD_NAME + "}"
    operational_env.write_text(
        f"{FIELD_NAME}={strong_value}\n{FIELD_NAME}={variable_reference}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "TARGET_FILES", [])
    monkeypatch.setattr(
        checker.sys,
        "argv",
        ["enforce_secret_strength.py", str(operational_env)],
    )

    assert checker.main() == 0
    assert "Secret strength checks passed." in capsys.readouterr().out


def test_banned_value_still_fails_in_the_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = tmp_path / ".env.example"
    banned_value = "pass" + "word"
    template.write_text(f"{FIELD_NAME}={banned_value}\n", encoding="utf-8")

    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "TARGET_FILES", [])
    monkeypatch.setattr(
        checker.sys,
        "argv",
        ["enforce_secret_strength.py", str(template)],
    )

    assert checker.main() == 1
    assert f"{template}:{FIELD_NAME} uses a weak value" in capsys.readouterr().out


def test_short_nonplaceholder_value_still_fails_the_length_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    operational_env = tmp_path / ".env"
    short_value = "_".join(("TINY", "VALUE"))
    assert len(short_value) < checker.MIN_LENGTH
    operational_env.write_text(f"{FIELD_NAME}={short_value}\n", encoding="utf-8")

    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "TARGET_FILES", [])
    monkeypatch.setattr(
        checker.sys,
        "argv",
        ["enforce_secret_strength.py", str(operational_env)],
    )

    assert checker.main() == 1
    assert (
        f"{operational_env}:{FIELD_NAME} uses a weak value" in capsys.readouterr().out
    )


def test_default_missing_files_are_silent_and_explicit_missing_path_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = tmp_path / ".env.example"
    placeholder = "_".join(("CHANGE", "ME"))
    template.write_text(f"{FIELD_NAME}={placeholder}\n", encoding="utf-8")
    target_names = {target.name for target in checker.TARGET_FILES}
    assert {".env", ".env.example", "docker-compose.yml"} <= target_names

    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(
        checker,
        "TARGET_FILES",
        [tmp_path / target.name for target in checker.TARGET_FILES],
    )
    monkeypatch.setattr(checker.sys, "argv", ["enforce_secret_strength.py"])

    assert checker.main() == 0
    assert "Warning:" not in capsys.readouterr().out

    missing = tmp_path / "missing.env"
    monkeypatch.setattr(
        checker.sys, "argv", ["enforce_secret_strength.py", str(missing)]
    )
    assert checker.main() == 0
    assert (
        f"Warning: requested file {missing} does not exist" in capsys.readouterr().out
    )


def test_template_symlink_cannot_exempt_operational_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path
    operational_env = root / ".env"
    placeholder = "_".join(("CHANGE", "ME"))
    operational_env.write_text(
        f"{FIELD_NAME}={placeholder}\n",
        encoding="utf-8",
    )
    template = root / ".env.example"
    template.symlink_to(operational_env)

    monkeypatch.setattr(checker, "ROOT", root)

    assert checker._check_lines(operational_env) == [
        f"{operational_env}:{FIELD_NAME} uses a weak value"
    ]


def test_symlinked_parent_cannot_alias_repository_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    template = root / ".env.example"
    placeholder = "_".join(("CHANGE", "ME"))
    template.write_text(
        f"{FIELD_NAME}={placeholder}\n",
        encoding="utf-8",
    )
    alias = tmp_path / "repo-alias"
    alias.symlink_to(root, target_is_directory=True)
    alias_template = alias / ".env.example"

    monkeypatch.setattr(checker, "ROOT", root)
    monkeypatch.setattr(checker, "TARGET_FILES", [])
    monkeypatch.setattr(
        checker.sys, "argv", ["enforce_secret_strength.py", str(alias_template)]
    )

    assert checker.main() == 1
    assert f"{alias_template}:{FIELD_NAME} uses a weak value" in capsys.readouterr().out
