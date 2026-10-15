from __future__ import annotations

import base64
import os
import secrets
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.config.base import (
    _MAX_SECRET_FILE_SIZE_BYTES,
    BaseAppSettings,
    _load_file_secret,
)
from app.core.config.database import DatabaseSettings


def _write_secret(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _testing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "testing")
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "CACHE_REDIS_URL",
        "REVOCATION_REDIS_URL",
        "AUDIT_LOG_SECRET",
        "CSRF_HMAC_SECRET",
        "IDEMPOTENCY_HMAC_SECRET",
        "INTERNAL_AUTH_TOKEN",
        "SPOTIFY_TOKEN_SECRET",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "CWV_RUM_SIGNING_SECRET",
        "MFA_EMAIL_OTP_HMAC_KEYS",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID",
        "MFA_EMAIL_DELIVERY_KEKS",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID",
        "MFA_TRUSTED_DEVICE_HMAC_KEYS",
        "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in (
        "DATABASE_URL_FILE",
        "SECRET_KEY_FILE",
        "CACHE_REDIS_URL_FILE",
        "REVOCATION_REDIS_URL_FILE",
        "AUDIT_LOG_SECRET_FILE",
        "CSRF_HMAC_SECRET_FILE",
        "IDEMPOTENCY_HMAC_SECRET_FILE",
        "INTERNAL_AUTH_TOKEN_FILE",
        "SPOTIFY_TOKEN_SECRET_FILE",
        "STORAGE_S3_ACCESS_KEY_ID_FILE",
        "STORAGE_S3_SECRET_ACCESS_KEY_FILE",
        "CWV_RUM_SIGNING_SECRET_FILE",
        "MFA_EMAIL_OTP_HMAC_KEYS_FILE",
        "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID_FILE",
        "MFA_EMAIL_DELIVERY_KEKS_FILE",
        "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID_FILE",
        "MFA_TRUSTED_DEVICE_HMAC_KEYS_FILE",
        "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_full_settings_boot_from_required_file_only_and_preserve_mfa_strings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _testing_environment(monkeypatch)
    database_url = "sqlite+aiosqlite:///./mounted-secret-settings.db"
    secret_key = secrets.token_urlsafe(32)
    database_file = _write_secret(tmp_path, "database-url", database_url)
    secret_key_file = _write_secret(tmp_path, "jwt-secret", secret_key)
    monkeypatch.setenv("DATABASE_URL_FILE", str(database_file))
    monkeypatch.setenv("SECRET_KEY_FILE", str(secret_key_file))

    cache_url = "redis://cache.invalid:6379/0"
    revocation_url = "redis://revocation.invalid:6379/0"
    cache_file = _write_secret(tmp_path, "cache-url", cache_url)
    revocation_file = _write_secret(tmp_path, "revocation-url", revocation_url)
    audit_secret = secrets.token_urlsafe(32)
    audit_file = _write_secret(tmp_path, "audit-secret", audit_secret)
    cwv_secret = secrets.token_urlsafe(32)
    cwv_file = _write_secret(tmp_path, "cwv-secret", cwv_secret)
    csrf_secret = secrets.token_urlsafe(32)
    csrf_file = _write_secret(tmp_path, "csrf-secret", csrf_secret)
    idempotency_secret = secrets.token_urlsafe(32)
    idempotency_file = _write_secret(tmp_path, "idempotency-secret", idempotency_secret)
    internal_token = secrets.token_urlsafe(32)
    internal_token_file = _write_secret(tmp_path, "internal-token", internal_token)
    spotify_secret = secrets.token_urlsafe(32)
    spotify_file = _write_secret(tmp_path, "spotify-secret", spotify_secret)
    s3_access = secrets.token_urlsafe(24)
    s3_access_file = _write_secret(tmp_path, "s3-access", s3_access)
    s3_secret = secrets.token_urlsafe(32)
    s3_secret_file = _write_secret(tmp_path, "s3-secret", s3_secret)
    for name, file_path in (
        ("CACHE_REDIS_URL_FILE", cache_file),
        ("REVOCATION_REDIS_URL_FILE", revocation_file),
        ("AUDIT_LOG_SECRET_FILE", audit_file),
        ("CWV_RUM_SIGNING_SECRET_FILE", cwv_file),
        ("CSRF_HMAC_SECRET_FILE", csrf_file),
        ("IDEMPOTENCY_HMAC_SECRET_FILE", idempotency_file),
        ("INTERNAL_AUTH_TOKEN_FILE", internal_token_file),
        ("SPOTIFY_TOKEN_SECRET_FILE", spotify_file),
        ("STORAGE_S3_ACCESS_KEY_ID_FILE", s3_access_file),
        ("STORAGE_S3_SECRET_ACCESS_KEY_FILE", s3_secret_file),
    ):
        monkeypatch.setenv(name, str(file_path))

    encoded_key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    key_ring = f"primary:{encoded_key}"
    ring_fields = (
        ("MFA_EMAIL_OTP_HMAC_KEYS", "mfa-email-otp-keys"),
        ("MFA_EMAIL_DELIVERY_KEKS", "mfa-email-delivery-keks"),
        ("MFA_TRUSTED_DEVICE_HMAC_KEYS", "mfa-trusted-device-keys"),
    )
    mfa_files: set[str] = set()
    for env_name, filename in ring_fields:
        ring_file = _write_secret(tmp_path, filename, key_ring)
        monkeypatch.setenv(f"{env_name}_FILE", str(ring_file))
        mfa_files.add(str(ring_file))
    for env_name, filename in (
        ("MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID", "otp-active-key-id"),
        ("MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID", "delivery-active-key-id"),
        ("MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID", "trusted-active-key-id"),
    ):
        active_file = _write_secret(tmp_path, filename, "primary")
        monkeypatch.setenv(f"{env_name}_FILE", str(active_file))
        mfa_files.add(str(active_file))

    tracked_files = {
        str(database_file),
        str(secret_key_file),
        str(cache_file),
        str(revocation_file),
        str(audit_file),
        str(cwv_file),
        str(csrf_file),
        str(idempotency_file),
        str(internal_token_file),
        str(spotify_file),
        str(s3_access_file),
        str(s3_secret_file),
    } | mfa_files
    read_counts: dict[str, int] = {}
    original_open = os.open

    def count_secret_opens(
        path: str | os.PathLike[str], flags: int, *args: object, **kwargs: object
    ) -> int:
        path_string = os.fspath(path)
        if path_string in tracked_files:
            read_counts[path_string] = read_counts.get(path_string, 0) + 1
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", count_secret_opens)
    settings = Settings()

    assert read_counts == {file_path: 1 for file_path in tracked_files}
    assert settings.database_url == database_url
    assert settings.secret_key == secret_key
    assert settings.cache_redis_url == cache_url
    assert settings.revocation_redis_url == revocation_url
    assert settings.audit_log_secret == audit_secret
    assert settings.cwv_rum_signing_secret.get_secret_value() == cwv_secret
    assert settings.csrf_hmac_secret == csrf_secret
    assert settings.idempotency_hmac_secret == idempotency_secret
    assert settings.internal_auth_token == internal_token
    assert settings.spotify_token_secret == spotify_secret
    assert settings.storage_s3_access_key_id == s3_access
    assert settings.storage_s3_secret_access_key == s3_secret
    assert settings.mfa_email_otp_hmac_keys == key_ring
    assert settings.mfa_email_delivery_keks == key_ring
    assert settings.mfa_trusted_device_hmac_keys == key_ring
    assert settings.mfa_email_otp_active_hmac_key_id == "primary"
    assert settings.mfa_email_delivery_active_kek_id == "primary"
    assert settings.mfa_trusted_device_active_hmac_key_id == "primary"
    assert settings.has_development_fallbacks is False
    assert "DATABASE_URL" not in os.environ
    assert "SECRET_KEY" not in os.environ
    loaded_values = (
        database_url,
        secret_key,
        cache_url,
        revocation_url,
        audit_secret,
        cwv_secret,
        csrf_secret,
        idempotency_secret,
        internal_token,
        spotify_secret,
        s3_access,
        s3_secret,
        key_ring,
    )
    if any(
        value in os.environ.values() or value in caplog.text for value in loaded_values
    ):
        pytest.fail("secret-file contents were copied to the environment or logs")


def test_unrelated_file_environment_name_is_not_loaded_by_a_narrow_settings_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "must-not-be-read"))
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///./narrow-model.db")
    assert settings.database_url == "sqlite+aiosqlite:///./narrow-model.db"


def test_file_environment_for_another_settings_model_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "unused-secret-file"))

    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///./narrow-model.db")

    assert settings.database_url == "sqlite+aiosqlite:///./narrow-model.db"


def test_validation_diagnostics_hide_mounted_secret_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_environment(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./diagnostic-test.db")
    monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(32))
    contents = "short-" + secrets.token_hex(6)
    audit_file = _write_secret(tmp_path, "invalid-audit-secret", contents)
    monkeypatch.setenv("AUDIT_LOG_SECRET_FILE", str(audit_file))

    with pytest.raises(ValidationError) as captured:
        Settings()

    if contents in str(captured.value):
        pytest.fail("mounted secret contents appeared in validation diagnostics")


def test_plain_environment_values_remain_supported_and_file_values_take_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_environment(monkeypatch)
    plain_database_url = "sqlite+aiosqlite:///./plain-env.db"
    plain_secret_key = secrets.token_urlsafe(32)
    monkeypatch.setenv("DATABASE_URL", plain_database_url)
    monkeypatch.setenv("SECRET_KEY", plain_secret_key)
    settings = Settings()
    assert settings.database_url == plain_database_url
    assert settings.secret_key == plain_secret_key

    mounted_database_url = "sqlite+aiosqlite:///./mounted-precedence.db"
    mounted_secret_key = secrets.token_urlsafe(32)
    database_file = _write_secret(tmp_path, "database-url", mounted_database_url)
    secret_file = _write_secret(tmp_path, "secret-key", mounted_secret_key)
    monkeypatch.setenv("DATABASE_URL_FILE", str(database_file))
    monkeypatch.setenv("SECRET_KEY_FILE", str(secret_file))
    settings = Settings()
    assert settings.database_url == mounted_database_url
    assert settings.secret_key == mounted_secret_key


def test_configured_required_file_failure_does_not_trigger_development_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_environment(monkeypatch)
    missing_file = tmp_path / "missing-database-url"
    secret_file = _write_secret(tmp_path, "secret-key", secrets.token_urlsafe(32))
    monkeypatch.setenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./plain-fallback-must-not-win.db"
    )
    monkeypatch.setenv("DATABASE_URL_FILE", str(missing_file))
    monkeypatch.setenv("SECRET_KEY_FILE", str(secret_file))

    with pytest.raises(ValidationError) as captured:
        Settings()

    assert "unable to read configured secret file for DATABASE_URL_FILE" in str(
        captured.value
    )
    assert str(missing_file) not in str(captured.value)
    assert not any(error["type"] == "missing" for error in captured.value.errors())


@pytest.mark.parametrize(
    ("env_name", "path_value", "file_bytes"),
    [
        ("TEST_SECRET_FILE", "", None),
        ("TEST_SECRET_FILE", "missing-file", None),
        ("TEST_SECRET_FILE", "invalid-utf8", b"\xff"),
        ("TEST_SECRET_FILE", "empty-file", b"  \n\t"),
    ],
)
def test_configured_file_inputs_fail_closed_without_disclosing_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    path_value: str,
    file_bytes: bytes | None,
) -> None:
    if path_value == "":
        monkeypatch.setenv(env_name, "  ")
    else:
        path = tmp_path / path_value
        if file_bytes is None:
            monkeypatch.setenv(env_name, str(path))
        else:
            path.write_bytes(file_bytes)
            monkeypatch.setenv(env_name, str(path))

    with pytest.raises(ValueError) as captured:
        _load_file_secret(env_name, "fallback-value")
    assert "fallback-value" not in str(captured.value)
    assert "invalid-utf8" not in str(captured.value)


def test_unconfigured_file_returns_plain_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_SECRET_FILE", raising=False)
    assert _load_file_secret("TEST_SECRET_FILE", "plain-value") == "plain-value"


def test_file_loader_follows_projected_secret_symlink_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version_dir = tmp_path / "..2026_10_15_000000"
    version_dir.mkdir()
    _write_secret(version_dir, "secret-key", "projected-secret-content")
    data_link = tmp_path / "..data"
    link = tmp_path / "secret-key"
    data_link.symlink_to(version_dir, target_is_directory=True)
    link.symlink_to(Path("..data") / "secret-key")
    monkeypatch.setenv("TEST_SECRET_FILE", str(link))
    assert _load_file_secret("TEST_SECRET_FILE", None) == "projected-secret-content"


def test_file_loader_rejects_directory_and_does_not_return_plain_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "directory-secret"
    directory.mkdir()
    monkeypatch.setenv("TEST_SECRET_FILE", str(directory))

    with pytest.raises(ValueError, match="must be a regular file") as captured:
        _load_file_secret("TEST_SECRET_FILE", "plain-fallback-value")

    assert "plain-fallback-value" not in str(captured.value)
    assert str(directory) not in str(captured.value)


def test_file_loader_rejects_nonregular_file_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_secret(tmp_path, "swapped-secret", "synthetic-secret-content")
    monkeypatch.setenv("TEST_SECRET_FILE", str(path))
    original_fstat = os.fstat

    def report_nonregular(descriptor: int) -> SimpleNamespace:
        info = original_fstat(descriptor)
        return SimpleNamespace(st_mode=stat.S_IFIFO, st_size=info.st_size)

    monkeypatch.setattr(os, "fstat", report_nonregular)

    with pytest.raises(ValueError, match="must be a regular file") as captured:
        _load_file_secret("TEST_SECRET_FILE", "plain-fallback-value")

    assert "plain-fallback-value" not in str(captured.value)
    assert "synthetic-secret-content" not in str(captured.value)
    assert str(path) not in str(captured.value)


def test_file_loader_rejects_oversized_file_without_disclosing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "oversized-secret"
    path.write_bytes(b"x" * (_MAX_SECRET_FILE_SIZE_BYTES + 1))
    monkeypatch.setenv("TEST_SECRET_FILE", str(path))

    with pytest.raises(ValueError, match="exceeds the size limit") as captured:
        _load_file_secret("TEST_SECRET_FILE", "plain-fallback-value")

    assert "plain-fallback-value" not in str(captured.value)
    assert str(path) not in str(captured.value)


def test_file_loader_caps_reads_when_file_grows_after_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "growing-secret"
    path.write_bytes(b"x" * (_MAX_SECRET_FILE_SIZE_BYTES + 9))
    monkeypatch.setenv("TEST_SECRET_FILE", str(path))

    original_open = os.open
    original_fstat = os.fstat
    original_read = os.read
    opened_descriptors: set[int] = set()
    requested_read_sizes: list[int] = []

    def track_open(
        opened_path: str | os.PathLike[str], flags: int, *args: object
    ) -> int:
        descriptor = original_open(opened_path, flags, *args)
        if os.fspath(opened_path) == str(path):
            opened_descriptors.add(descriptor)
        return descriptor

    def report_small_file(descriptor: int) -> os.stat_result:
        info = original_fstat(descriptor)
        if descriptor not in opened_descriptors:
            return info
        fields = list(info)
        fields[6] = 1
        return os.stat_result(fields)

    def count_bounded_read(descriptor: int, size: int) -> bytes:
        if descriptor in opened_descriptors:
            requested_read_sizes.append(size)
        return original_read(descriptor, size)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "fstat", report_small_file)
    monkeypatch.setattr(os, "read", count_bounded_read)

    with pytest.raises(ValueError, match="exceeds the size limit"):
        _load_file_secret("TEST_SECRET_FILE", None)

    assert sum(requested_read_sizes) == _MAX_SECRET_FILE_SIZE_BYTES + 1
    assert max(requested_read_sizes) <= 64 * 1024


def test_file_loader_sanitizes_read_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_secret(tmp_path, "unreadable-secret", "synthetic-file-content")
    monkeypatch.setenv("TEST_SECRET_FILE", str(path))

    def fail_read(descriptor: int, size: int) -> bytes:
        raise PermissionError("synthetic read failure with secret-shaped detail")

    monkeypatch.setattr(os, "read", fail_read)

    with pytest.raises(
        ValueError, match="unable to read configured secret file for TEST_SECRET_FILE"
    ) as captured:
        _load_file_secret("TEST_SECRET_FILE", "plain-fallback-value")

    assert "synthetic read failure" not in str(captured.value)
    assert "synthetic-file-content" not in str(captured.value)
    assert "plain-fallback-value" not in str(captured.value)


def test_file_loader_keeps_secret_when_descriptor_close_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_secret(tmp_path, "close-error-secret", "valid-secret-content")
    monkeypatch.setenv("TEST_SECRET_FILE", str(path))
    original_close = os.close

    def close_then_report_error(descriptor: int) -> None:
        original_close(descriptor)
        raise OSError("synthetic close failure")

    monkeypatch.setattr(os, "close", close_then_report_error)

    assert _load_file_secret("TEST_SECRET_FILE", None) == "valid-secret-content"


@pytest.mark.skipif(
    not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"),
    reason="FIFO checks require POSIX nonblocking file opens",
)
def test_file_loader_rejects_fifo_raced_after_regular_file_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fifo = tmp_path / "secret-fifo"
    os.mkfifo(fifo)
    regular_path = _write_secret(tmp_path, "regular-file", "regular")
    regular_info = regular_path.stat()
    original_stat = Path.stat
    original_open = os.open
    spoofed_stat = False
    observed_nonblocking_open = False

    def report_regular_once(
        path: Path, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal spoofed_stat
        if path == fifo and not spoofed_stat:
            spoofed_stat = True
            return regular_info
        return original_stat(path, *args, **kwargs)

    def require_nonblocking_open(
        path: str | os.PathLike[str], flags: int, *args: object
    ) -> int:
        nonlocal observed_nonblocking_open
        if os.fspath(path) == str(fifo):
            observed_nonblocking_open = bool(flags & os.O_NONBLOCK)
            assert observed_nonblocking_open
        return original_open(path, flags, *args)

    monkeypatch.setattr(Path, "stat", report_regular_once)
    monkeypatch.setattr(os, "open", require_nonblocking_open)
    monkeypatch.setenv("TEST_SECRET_FILE", str(fifo))

    with pytest.raises(ValueError, match="must be a regular file"):
        _load_file_secret("TEST_SECRET_FILE", None)

    assert spoofed_stat is True
    assert observed_nonblocking_open is True


def test_base_model_validator_rejects_non_mapping_input() -> None:
    with pytest.raises(ValidationError):
        BaseAppSettings.model_validate(None)
