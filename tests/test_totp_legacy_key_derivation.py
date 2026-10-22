from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import scripts.derive_legacy_totp_key_entry as legacy_derivation
from scripts.derive_legacy_totp_key_entry import (
    derive_legacy_totp_key_entry,
    main,
)


def test_legacy_entry_matches_historical_spotify_fallback_without_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical_secret = secrets.token_urlsafe(32)
    source = tmp_path / "historical-secret"
    output = tmp_path / "legacy-entry"
    source.write_text(f"  {historical_secret}  ", encoding="utf-8")
    monkeypatch.setattr(legacy_derivation, "_PLATFORM_NAME", "posix")
    legacy_token = Fernet(
        base64.urlsafe_b64encode(
            hashlib.sha256(historical_secret.encode("utf-8")).digest()
        )
    ).encrypt(b"legacy-enrollment")

    assert (
        main(
            [
                "--historical-secret-key-file",
                str(source),
                "--output-file",
                str(output),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert historical_secret not in captured.out
    assert historical_secret not in captured.err
    assert "key entry written" in captured.out
    key_id, separator, encoded_key = (
        output.read_text(encoding="ascii").strip().partition(":")
    )
    assert separator and key_id == "legacy-spotify-derived"
    assert encoded_key not in captured.out
    assert encoded_key not in captured.err
    assert (
        Fernet(encoded_key.encode("ascii")).decrypt(legacy_token)
        == b"legacy-enrollment"
    )
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600


def test_legacy_entry_never_overwrites_output_or_displays_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical_secret = secrets.token_urlsafe(32)
    source = tmp_path / "historical-secret"
    output = tmp_path / "existing-entry"
    source.write_text(historical_secret, encoding="utf-8")
    output.write_text("keep-existing-content", encoding="ascii")
    monkeypatch.setattr(legacy_derivation, "_PLATFORM_NAME", "posix")

    assert (
        main(
            [
                "--historical-secret-key-file",
                str(source),
                "--output-file",
                str(output),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    expected_key = base64.urlsafe_b64encode(
        hashlib.sha256(historical_secret.encode("utf-8")).digest()
    ).decode("ascii")
    assert historical_secret not in captured.out
    assert historical_secret not in captured.err
    assert expected_key not in captured.out
    assert expected_key not in captured.err
    assert "key material was displayed" in captured.err
    assert output.read_text(encoding="ascii") == "keep-existing-content"


@pytest.mark.parametrize("contents", ("", "\xff"))
def test_legacy_entry_rejects_empty_or_non_utf8_source(
    tmp_path: Path, contents: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "historical-secret"
    output = tmp_path / "legacy-entry"
    monkeypatch.setattr(legacy_derivation, "_PLATFORM_NAME", "posix")
    if contents == "\xff":
        source.write_bytes(b"\xff")
    else:
        source.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError):
        derive_legacy_totp_key_entry(source, output)
    assert not output.exists()


def test_legacy_entry_rejects_oversized_historical_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "historical-secret"
    output = tmp_path / "legacy-entry"
    source.write_bytes(b"x" * 4097)
    monkeypatch.setattr(legacy_derivation, "_PLATFORM_NAME", "posix")

    with pytest.raises(ValueError, match="exceeds the allowed size"):
        derive_legacy_totp_key_entry(source, output)
    assert not output.exists()


def test_legacy_entry_refuses_filesystems_without_posix_mode_guarantees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    historical_secret = secrets.token_urlsafe(32)
    source = tmp_path / "historical-secret"
    output = tmp_path / "legacy-entry"
    source.write_text(historical_secret, encoding="utf-8")
    monkeypatch.setattr(legacy_derivation, "_PLATFORM_NAME", "nt")

    assert (
        main(
            [
                "--historical-secret-key-file",
                str(source),
                "--output-file",
                str(output),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "no key material was displayed" in captured.err
    assert historical_secret not in captured.out + captured.err
    assert str(source) not in captured.out + captured.err
    assert str(output) not in captured.out + captured.err
    assert not output.exists()
