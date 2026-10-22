"""Fail-closed contract for the reviewed frozen-RC manifest and its CLI."""

from __future__ import annotations

import io
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quality" / "resolve_frozen_rc_manifest.py"
ERROR = "ERROR: frozen RC manifest is invalid or not frozen\n"


def _document(source_sha: object = "a" * 40) -> dict[str, object]:
    return {"schema_version": 1, "source_sha": source_sha}


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    manifest: Path,
) -> tuple[int, str, str]:
    assert SCRIPT.is_file(), "the frozen-RC manifest validator must be implemented"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--manifest", str(manifest)])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert isinstance(stopped.value.code, int)
    output = capsys.readouterr()
    return stopped.value.code, output.out, output.err


def test_valid_manifest_emits_only_the_exact_sha(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(json.dumps(_document()), encoding="utf-8")

    assert _run_cli(monkeypatch, capsys, manifest) == (0, "a" * 40 + "\n", "")


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        True,
        1,
        "fixture marker",
        {},
        {"schema_version": 1},
        {"source_sha": "a" * 40},
        {**_document(), "extra": "fixture marker"},
        {**_document(), "schema_version": True},
        {**_document(), "schema_version": "1"},
        {**_document(), "schema_version": 2},
    ],
)
def test_manifest_shape_and_version_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    document: object,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


@pytest.mark.parametrize(
    "source_sha",
    [
        None,
        "",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "g" * 40,
        "a" * 40 + "\n",
        " " + "a" * 40,
        "a" * 40 + " ",
        1,
        False,
        [],
        {},
    ],
)
def test_unfrozen_or_invalid_commit_fails_without_echoing_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    source_sha: object,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(json.dumps(_document(source_sha)), encoding="utf-8")

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


@pytest.mark.parametrize(
    "raw",
    [b"", b"{fixture marker", b"\xff", b"[" * 1500 + b"0" + b"]" * 1500],
)
def test_malformed_or_non_utf8_manifest_has_a_sanitized_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    raw: bytes,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_bytes(raw)

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


@pytest.mark.parametrize("duplicate_key", ["schema_version", "source_sha"])
def test_duplicate_manifest_fields_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    duplicate_key: str,
) -> None:
    document = _document()
    raw = json.dumps(document)[:-1]
    raw += ", " + json.dumps(duplicate_key) + ": "
    raw += json.dumps(document[duplicate_key]) + "}"
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(raw, encoding="utf-8")

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


def test_missing_manifest_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert _run_cli(monkeypatch, capsys, tmp_path / "missing.json") == (1, "", ERROR)


def test_directory_is_not_a_manifest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert _run_cli(monkeypatch, capsys, tmp_path) == (1, "", ERROR)


def test_nonregular_manifest_is_rejected_before_open(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "nonregular.json"
    manifest.write_text(json.dumps(_document()), encoding="utf-8")
    original_is_file = Path.is_file
    original_open = Path.open

    def is_regular(path: Path) -> bool:
        return False if path == manifest else original_is_file(path)

    def guarded_open(path: Path, *args: object, **kwargs: object) -> object:
        assert path != manifest, "nonregular manifests must not be opened"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_regular)
    monkeypatch.setattr(Path, "open", guarded_open)

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


def test_symlink_manifest_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_document()), encoding="utf-8")
    manifest = tmp_path / "frozen-rc.json"
    manifest.symlink_to(target)

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


@pytest.mark.parametrize("size, expected_code", [(4096, 0), (4097, 1)])
def test_manifest_size_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    size: int,
    expected_code: int,
) -> None:
    raw = json.dumps(_document()).encode("utf-8")
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_bytes(raw + b" " * (size - len(raw)))

    expected = (0, "a" * 40 + "\n", "") if expected_code == 0 else (1, "", ERROR)
    assert _run_cli(monkeypatch, capsys, manifest) == expected


def test_manifest_read_is_bounded_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(json.dumps(_document()), encoding="utf-8")
    original_open = Path.open

    class BoundedManifest(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            assert size == 4097, "read only the size cap plus one sentinel byte"
            return super().read(size)

    def bounded_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == manifest:
            return BoundedManifest(b" " * 4097)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", bounded_open)

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


def test_manifest_parser_has_no_cli_side_effects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert SCRIPT.is_file(), "the frozen-RC manifest validator must be implemented"
    namespace = runpy.run_path(str(SCRIPT), run_name="frozen_rc_contract")
    parse_manifest = namespace["parse_manifest"]

    assert parse_manifest(_document()) == "a" * 40
    with pytest.raises(ValueError):
        parse_manifest(_document(None))
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_manifest_read_error_does_not_expose_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "frozen-rc.json"
    manifest.write_text(json.dumps(_document()), encoding="utf-8")

    def failing_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("fixture marker")

    monkeypatch.setattr(Path, "open", failing_open)

    assert _run_cli(monkeypatch, capsys, manifest) == (1, "", ERROR)


def test_checked_in_manifest_has_only_the_reviewed_selection_fields() -> None:
    manifest = ROOT / "quality" / "frozen-rc.json"
    assert manifest.is_file(), "the reviewed frozen-RC manifest must be tracked"
    document = json.loads(manifest.read_text(encoding="utf-8"))

    assert isinstance(document, dict)
    assert set(document) == {"schema_version", "source_sha"}
    assert type(document["schema_version"]) is int
    assert document["schema_version"] == 1
    source_sha = document["source_sha"]
    assert source_sha is None or (
        isinstance(source_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None
    )
