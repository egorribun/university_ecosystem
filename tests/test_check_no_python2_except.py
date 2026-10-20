"""Behavioral contracts for the Python-2 except syntax check."""

import os
from pathlib import Path

import pytest

from scripts import check_no_python2_except as CHECKER_MODULE


def _git(cwd: Path, *args: str) -> None:
    CHECKER_MODULE._run_git(list(args), cwd=cwd)


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "--quiet")
    _git(path, "config", "user.name", "Contract Test")
    _git(path, "config", "user.email", "contract-test@example.invalid")
    _git(path, "config", "core.hooksPath", str(path / "no-hooks"))
    return path


def _run_checker(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    monkeypatch.chdir(cwd)
    try:
        CHECKER_MODULE.main()
    except SystemExit as error:
        code = error.code
    else:
        code = 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _stage(path: Path, filename: str, content: str) -> None:
    target = path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(path, "add", "--", filename)


def test_clean_index_scans_tracked_python_for_legacy_except(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "legacy.py", "try:\n    pass\nexcept ValueError, error:\n    pass\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")

    code, stdout, _ = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "legacy.py:3:" in stdout


def test_clean_index_scans_unstaged_worktree_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "legacy.py", "value = 1\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    (repo / "legacy.py").write_text(
        "try:\n    pass\nexcept ValueError, error:\n    pass\n", encoding="utf-8"
    )

    code, stdout, _ = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "legacy.py:3:" in stdout


def test_token_controls_ignore_comments_and_strings_and_allow_tuple_except(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(
        repo,
        "valid.py",
        "# except ValueError, error:\n"
        'example = "except ValueError, error:"\n'
        "try:\n    pass\n"
        "except (ValueError, TypeError) as error:\n    pass\n",
    )

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 0, stdout + stderr


def test_staged_exception_expression_comma_binding_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(
        repo,
        "legacy.py",
        "try:\n    pass\nexcept errors.ValueError, error:\n    pass\n",
    )

    code, stdout, _ = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "legacy.py:3:" in stdout


def test_tokenization_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "broken.py", 'example = """unterminated\n')

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "Unable to tokenize tracked Python file" in stderr
    assert not stdout


def test_staged_bytes_take_precedence_over_invalid_worktree_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "sample.py", "value = 1\n")
    (repo / "sample.py").write_text(
        "try:\n    pass\nexcept ValueError, error:\n    pass\n", encoding="utf-8"
    )

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 0, stdout + stderr


def test_staged_invalid_bytes_are_checked_even_if_worktree_is_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "sample.py", "try:\n    pass\nexcept ValueError, error:\n    pass\n")
    (repo / "sample.py").write_text("value = 1\n", encoding="utf-8")

    code, stdout, _ = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "sample.py:3:" in stdout


def test_git_enumeration_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, stderr = _run_checker(tmp_path, monkeypatch, capsys)

    assert code == 1
    assert "could not complete" in stderr
    assert not stdout


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "message"),
    [
        ("MAX_TRACKED_PYTHON_FILES", 0, "file count exceeded"),
        ("MAX_PYTHON_FILE_BYTES", 0, "file exceeded"),
        ("MAX_TOTAL_PYTHON_BYTES", 0, "source total exceeded"),
    ],
)
def test_clean_index_scan_limits_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    limit_name: str,
    limit_value: int,
    message: str,
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "sample.py", "value = 1\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    monkeypatch.setattr(CHECKER_MODULE, limit_name, limit_value)

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert message in stderr
    assert not stdout


def test_staged_rename_is_scanned_with_other_staged_python_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    original = "".join(f"value_{index} = {index}\n" for index in range(100))
    _stage(repo, "old_name.py", original)
    _stage(repo, "other.py", "value = 1\n")
    _git(repo, "config", "diff.renames", "true")
    _git(repo, "commit", "--quiet", "-m", "fixture")

    (repo / "old_name.py").rename(repo / "renamed.py")
    (repo / "renamed.py").write_text(
        original + "try:\n    pass\nexcept ValueError, error:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "other.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", "-A")

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1, stdout + stderr
    assert "renamed.py:" in stdout


def test_staged_python_type_change_fails_closed_with_other_python_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "changed.py", "value = 1\n")
    _stage(repo, "other.py", "value = 1\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")

    pointer = repo / "pointer.txt"
    pointer.write_text("target.py\n", encoding="utf-8")
    object_id = (
        CHECKER_MODULE._run_git(["hash-object", "-w", str(pointer)], cwd=repo)
        .decode("ascii")
        .strip()
    )
    _git(repo, "update-index", "--cacheinfo", f"120000,{object_id},changed.py")
    (repo / "other.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", "--", "other.py")

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "type" in stderr.lower()
    assert not stdout


def test_unmerged_python_index_entry_fails_closed_with_other_python_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(repo, "conflict.py", "value = 1\n")
    _stage(repo, "other.py", "value = 1\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")

    primary_branch = (
        CHECKER_MODULE._run_git(["branch", "--show-current"], cwd=repo)
        .decode("ascii")
        .strip()
    )
    _git(repo, "checkout", "--quiet", "-b", "side")
    (repo / "conflict.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", "--", "conflict.py")
    _git(repo, "commit", "--quiet", "-m", "side change")
    _git(repo, "checkout", "--quiet", primary_branch)
    (repo / "conflict.py").write_text("value = 3\n", encoding="utf-8")
    _git(repo, "add", "--", "conflict.py")
    _git(repo, "commit", "--quiet", "-m", "primary change")
    with pytest.raises(CHECKER_MODULE.ScanError, match="Git source query failed"):
        _git(repo, "merge", "side")
    (repo / "other.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", "--", "other.py")

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "merge stages" in stderr.lower()
    assert not stdout


def test_clean_index_rejects_out_of_root_directory_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    nested = repo / "nested"
    nested.mkdir()
    _stage(repo, "nested/tracked.py", "value = 1\n")
    _git(repo, "commit", "--quiet", "-m", "fixture")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "tracked.py").write_text("value = 2\n", encoding="utf-8")
    (nested / "tracked.py").unlink()
    nested.rmdir()
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(outside), str(nested))
        assert nested.is_junction()
    else:
        nested.symlink_to(outside, target_is_directory=True)
        assert nested.is_symlink()

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "path" in stderr.lower() or "repository" in stderr.lower()
    assert not stdout


def test_worktree_read_rejects_file_changed_after_descriptor_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path / "repo")
    target = repo / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    real_read = CHECKER_MODULE.os.read
    changed = False

    def read_then_change(descriptor: int, size: int) -> bytes:
        nonlocal changed
        content = real_read(descriptor, size)
        if not changed:
            changed = True
            target.write_text("value = 222\n", encoding="utf-8")
        return content

    monkeypatch.setattr(CHECKER_MODULE.os, "read", read_then_change)

    with pytest.raises(CHECKER_MODULE.ScanError, match="changed while"):
        CHECKER_MODULE.read_worktree_content(repo, "sample.py")


def test_staged_added_symlink_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    pointer = repo / "pointer.txt"
    pointer.write_text("safe.py\n", encoding="utf-8")
    object_id = (
        CHECKER_MODULE._run_git(["hash-object", "-w", str(pointer)], cwd=repo)
        .decode("ascii")
        .strip()
    )
    _git(repo, "update-index", "--add", "--cacheinfo", f"120000,{object_id},added.py")

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1
    assert "regular file" in stderr.lower() or "type" in stderr.lower()
    assert not stdout


def test_staged_executable_regular_python_file_is_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repository(tmp_path / "repo")
    _stage(
        repo,
        "executable.py",
        "try:\n    pass\nexcept ValueError, error:\n    pass\n",
    )
    _git(repo, "update-index", "--chmod=+x", "--", "executable.py")

    code, stdout, stderr = _run_checker(repo, monkeypatch, capsys)

    assert code == 1, stderr
    assert "executable.py:3:" in stdout
