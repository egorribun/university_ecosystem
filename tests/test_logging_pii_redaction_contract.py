"""Exact PII redaction contract for structured log events."""

from __future__ import annotations

import ast
import json
import logging
from contextvars import Context
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

import app.core.logging as logging_mod
from app.core.logging import (
    _normalize_field_name,
    _redact_free_text,
    _redact_nested,
    _redact_pii,
)

REDACTED = "[REDACTED]"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("APIKey", "api_key"),
        ("accessToken", "access_token"),
        ("X-Api-Key", "x_api_key"),
        ("__Email__", "email"),
        ("sessionID", "session_id"),
        ("CSRFToken", "csrf_token"),
        ("Set-Cookie", "set_cookie"),
        ("refresh-token", "refresh_token"),
        ("PHONE", "phone"),
    ],
)
def test_field_names_normalize_across_naming_styles(raw: str, normalized: str) -> None:
    assert _normalize_field_name(raw) == normalized


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call +1 555 123 4567", f"call {REDACTED}"),
        ("reach me at 555-123-4567", f"reach me at {REDACTED}"),
        ("phone: 555.123.4567", f"phone: {REDACTED}"),
        ("+7 999.123.4567", REDACTED),
        ("write a@b.cc", f"write {REDACTED}"),
        # Explicit non-phone context and dotted numbers without phone context
        # (versions, build numbers) stay readable.
        ("build 555-0199", "build 555-0199"),
        ("see 555.123.4567", "see 555.123.4567"),
    ],
)
def test_free_text_redacts_contacts_but_keeps_numeric_identifiers(
    text: str, expected: str
) -> None:
    assert _redact_free_text(text) == expected


def test_the_shortest_email_is_redacted_inside_structures() -> None:
    assert _redact_nested("a@b.cc", seen=set()) == REDACTED


def test_nested_mappings_lists_and_tuples_are_redacted_in_place() -> None:
    payload: dict[str, Any] = {
        "user": {
            "password": "hunter2",  # pragma: allowlist secret
            "note": "mail a@b.cc",
        },
        "items": [["call 555-123-4567"], {"token": "t"}],
        "pair": ("a@b.cc", 5),
        "nested_pair": (("a@b.cc",), 5),
    }

    result = _redact_nested(payload, seen=set())

    assert result is payload
    assert payload == {
        "user": {"password": REDACTED, "note": f"mail {REDACTED}"},
        "items": [[f"call {REDACTED}"], {"token": REDACTED}],
        "pair": (REDACTED, 5),
        "nested_pair": ((REDACTED,), 5),
    }


def test_shared_values_are_redacted_every_time_they_appear() -> None:
    shared_dict = {"note": "a@b.cc"}
    shared_list = ["a@b.cc"]
    shared_tuple = ("a@b.cc",)
    payload = {
        "d1": shared_dict,
        "d2": shared_dict,
        "l1": shared_list,
        "l2": shared_list,
        "t1": shared_tuple,
        "t2": shared_tuple,
    }

    _redact_nested(payload, seen=set())

    assert payload["d2"] is shared_dict
    assert shared_dict == {"note": REDACTED}
    assert payload["l2"] is shared_list
    assert shared_list == [REDACTED]
    assert payload["t1"] == payload["t2"] == (REDACTED,)


def test_cycles_are_replaced_instead_of_recursing_forever() -> None:
    cyclic_dict: dict[str, Any] = {"note": "ok"}
    cyclic_dict["self"] = cyclic_dict
    cyclic_list: list[Any] = ["ok"]
    cyclic_list.append(cyclic_list)

    assert _redact_nested(cyclic_dict, seen=set()) == {"note": "ok", "self": REDACTED}
    assert _redact_nested(cyclic_list, seen=set()) == ["ok", REDACTED]


def test_event_dict_redaction_covers_fields_values_and_self_references() -> None:
    event: dict[str, Any] = {
        "event": "login for a@b.cc",
        "Authorization": "Bearer secret",  # pragma: allowlist secret
        "context": {"refreshToken": "r", "detail": "call 555-123-4567"},
    }
    event["loop"] = event

    result = _redact_pii(None, "info", event)

    assert result is event
    assert event == {
        "event": f"login for {REDACTED}",
        "Authorization": REDACTED,
        "context": {"refreshToken": REDACTED, "detail": f"call {REDACTED}"},
        "loop": REDACTED,
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "reset_token",
        "reset-token",
        "resetToken",
        "ResetToken",
        "RESET_TOKEN",
        "csrf_hmac_secret",
        "csrf-hmac-secret",
        "csrfHmacSecret",
        "CsrfHmacSecret",
        "CSRF_HMAC_SECRET",
    ],
)
def test_account_recovery_and_csrf_fields_are_redacted_at_every_depth(
    field_name: str,
) -> None:
    """AUD-359: credential-bearing fields must not fall back to text matching."""
    event = {
        field_name: "synthetic-value",
        "details": [{"nested": {field_name: "synthetic-value"}}],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: REDACTED,
        "details": [{"nested": {field_name: REDACTED}}],
    }


def test_sensitive_field_matching_preserves_related_nonsecret_metadata() -> None:
    """AUD-359: fixing exact names must not mask all token/secret-prefixed keys."""
    event = {
        "event": "security configuration inspected",
        "reset_token_count": 7,
        "reset_token_expiry_minutes": 45,
        "csrf_hmac_secret_configured": True,
        "token_type": "Bearer",
        "secret_name": "csrf-signing-key",
        "details": {
            "resetTokenCount": 7,
            "csrfHmacSecretConfigured": True,
            "status": "configured",
        },
    }

    assert _redact_pii(None, "info", event) == {
        "event": "security configuration inspected",
        "reset_token_count": 7,
        "reset_token_expiry_minutes": 45,
        "csrf_hmac_secret_configured": True,
        "token_type": "Bearer",
        "secret_name": "csrf-signing-key",
        "details": {
            "resetTokenCount": 7,
            "csrfHmacSecretConfigured": True,
            "status": "configured",
        },
    }


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("field_name", ["reset_token", "csrf_hmac_secret"])
def test_account_recovery_and_csrf_values_never_reach_log_renderers(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    field_name: str,
) -> None:
    """Exercise the real configured processor chain and its emitted output."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    sensitive_value = "synthetic-value"

    try:
        logging_mod.configure_logging(json_output=json_output)
        logger = logging_mod.get_logger("audit-359-regression").bind(
            **{field_name: sensitive_value}
        )
        logger.info(
            "security configuration inspected",
            details={"items": [{field_name: sensitive_value}]},
            status="public-diagnostic",
        )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "security configuration inspected" in output
    assert "public-diagnostic" in output
    assert field_name in output
    assert sensitive_value not in output
    assert output.count(REDACTED) == 2
    if json_output:
        rendered = json.loads(output)
        assert rendered[field_name] == REDACTED
        assert rendered["details"] == {"items": [{field_name: REDACTED}]}
        assert rendered["status"] == "public-diagnostic"


@pytest.mark.parametrize(
    "field_name",
    [
        "challenge_token",
        "challenge-token",
        "challengeToken",
        "ChallengeToken",
        "CHALLENGE_TOKEN",
        "nats_auth_token",
        "current_password",
        "new_password",
        "new-password",
        "newPassword",
        "NewPassword",
        "NEW_PASSWORD",
        "smtp_password",
        "elasticsearch_password",
        "token_hmac_secret",
        "token-hmac-secret",
        "tokenHmacSecret",
        "TokenHmacSecret",
        "TOKEN_HMAC_SECRET",
        "internal_hmac_secret",
        "audit_log_secret",
        "jwt_signing_active_secret",
        "spotify_client_secret",
        "spotify_token_secret",
        "spotify_oauth_state_secret",
        "ws_hub_internal_secret",
        "idempotency_hmac_secret",
        "cwv_rum_signing_secret",
    ],
)
def test_terminal_credential_families_are_redacted_at_every_depth(
    field_name: str,
) -> None:
    """AUD-359: actual schema/config credentials share terminal word families."""
    sensitive_value = "synthetic-value"
    event = {
        field_name: sensitive_value,
        "details": [({field_name: sensitive_value},)],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: REDACTED,
        "details": [({field_name: REDACTED},)],
    }


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("secret_key", "synthetic-value"),
        ("SECRET_KEY", "synthetic-value"),
        ("signing_key", "synthetic-value"),
        ("signingKey", "synthetic-value"),
        (
            "jwt_signing_keys",
            ["primary:synthetic-value", "previous:synthetic-value"],
        ),
        (
            "jwt_signing_key_registry",
            {"primary": "synthetic-value", "previous": "synthetic-value"},
        ),
        (
            "jwtSigningKeyRegistry",
            {"primary": "synthetic-value", "previous": "synthetic-value"},
        ),
        ("mfa_totp_encryption_keys", "synthetic-value"),
        ("MFA_TOTP_ENCRYPTION_KEYS", "synthetic-value"),
        ("mfa_email_otp_hmac_keys", "synthetic-value"),
        ("mfa-email-otp-hmac-keys", "synthetic-value"),
        ("mfa_email_delivery_keks", "synthetic-value"),
        ("mfa_trusted_device_hmac_keys", "synthetic-value"),
        ("storage_s3_secret_access_key", "synthetic-value"),
        ("storageS3SecretAccessKey", "synthetic-value"),
        ("vapid_private_key", "synthetic-value"),
        ("spicedb_preshared_key", "synthetic-value"),
        ("otpauth_url", "synthetic-value"),
        ("otpauthUrl", "synthetic-value"),
        ("imgproxy_key", "synthetic-value"),
        ("imgproxy_salt", "synthetic-value"),
    ],
    ids=[
        "secret_key",
        "SECRET_KEY",
        "signing_key",
        "signingKey",
        "jwt_signing_keys",
        "jwt_signing_key_registry",
        "jwtSigningKeyRegistry",
        "mfa_totp_encryption_keys",
        "MFA_TOTP_ENCRYPTION_KEYS",
        "mfa_email_otp_hmac_keys",
        "mfa-email-otp-hmac-keys",
        "mfa_email_delivery_keks",
        "mfa_trusted_device_hmac_keys",
        "storage_s3_secret_access_key",
        "storageS3SecretAccessKey",
        "vapid_private_key",
        "spicedb_preshared_key",
        "otpauth_url",
        "otpauthUrl",
        "imgproxy_key",
        "imgproxy_salt",
    ],
)
def test_known_key_material_and_keyrings_are_redacted_as_complete_values(
    field_name: str, field_value: Any
) -> None:
    """AUD-359: key IDs inside a credential registry do not make its values public."""
    event = {
        field_name: field_value,
        "details": [{field_name: field_value}],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: REDACTED,
        "details": [{field_name: REDACTED}],
    }


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("token_type", "Bearer"),
        ("access_token_expire_minutes", 60),
        ("reset_token_count", 7),
        ("challenge-token-count", 2),
        ("csrfHmacSecretConfigured", True),
        ("newPasswordConfigured", True),
        ("mfaTotpEncryptionKeysConfigured", True),
        ("mfa_totp_active_encryption_key_id", "primary"),
        ("MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID", "primary"),
        ("mfa_email_otp_active_hmac_key_id", "primary"),
        ("mfa_email_delivery_active_kek_id", "primary"),
        ("mfa_trusted_device_active_hmac_key_id", "primary"),
        ("jwt_active_kid", "primary"),
        ("jwt_signing_active_kid", "primary"),
        ("storage_s3_access_key_id", "public-identifier"),
        ("vapid_public_key", "public-material"),
        ("vapidPublicKey", "public-material"),
        ("public_key", "public-material"),
        ("jwt_private_key_path", "mounted-path"),
        ("tokenizer", "ready"),
        ("secretary", "ready"),
        ("password_policy", "standard"),
        ("cache_key", "public-cache-slot"),
        ("key", "public-slot"),
        ("id", "public-id"),
        ("notatoken", "public-label"),
        ("notasecret", "public-label"),
        ("notapassword", "public-label"),
        ("user_id", "public-user-id"),
        ("error_code", "validation_failed"),
        ("code", "validation_failed"),
        ("codes", ["validation_failed"]),
    ],
    ids=[
        "token_type",
        "access_token_expire_minutes",
        "reset_token_count",
        "challenge-token-count",
        "csrfHmacSecretConfigured",
        "newPasswordConfigured",
        "mfaTotpEncryptionKeysConfigured",
        "mfa_totp_active_encryption_key_id",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "mfa_email_otp_active_hmac_key_id",
        "mfa_email_delivery_active_kek_id",
        "mfa_trusted_device_active_hmac_key_id",
        "jwt_active_kid",
        "jwt_signing_active_kid",
        "storage_s3_access_key_id",
        "vapid_public_key",
        "vapidPublicKey",
        "public_key",
        "jwt_private_key_path",
        "tokenizer",
        "secretary",
        "password_policy",
        "cache_key",
        "key",
        "id",
        "notatoken",
        "notasecret",
        "notapassword",
        "user_id",
        "error_code",
        "code",
        "codes",
    ],
)
def test_credential_classification_preserves_public_metadata_and_nonsecret_words(
    field_name: str, field_value: Any
) -> None:
    """Suffixes must be terminal words; generic key/id/code fields are not secrets."""
    event = {
        field_name: deepcopy(field_value),
        "details": [{field_name: deepcopy(field_value)}],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: field_value,
        "details": [{field_name: field_value}],
    }


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("challengeToken", "synthetic-value"),
        ("smtp-password", "synthetic-value"),
        ("jwtSigningActiveSecret", "synthetic-value"),
        ("mfaTotpEncryptionKeys", "synthetic-value"),
        (
            "jwtSigningKeyRegistry",
            {"primary": "synthetic-value", "previous": "synthetic-value"},
        ),
    ],
    ids=[
        "challengeToken",
        "smtp-password",
        "jwtSigningActiveSecret",
        "mfaTotpEncryptionKeys",
        "jwtSigningKeyRegistry",
    ],
)
def test_context_bound_credential_families_and_keyrings_never_reach_renderers(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    field_name: str,
    field_value: Any,
) -> None:
    """Both renderers redact contextvars merged into a real configured log event."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    context = Context()

    try:
        logging_mod.configure_logging(json_output=json_output)
        context.run(logging_mod.bind_context, **{field_name: field_value})
        logger = logging_mod.get_logger("audit-359-context-regression")
        context.run(
            logger.info,
            "credential configuration inspected",
            details={"items": [{field_name: field_value}]},
            status="public-diagnostic",
            token_type="Bearer",
        )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "credential configuration inspected" in output
    assert "public-diagnostic" in output
    assert "Bearer" in output
    assert field_name in output
    assert "synthetic-value" not in output
    assert output.count(REDACTED) == 2
    if json_output:
        rendered = json.loads(output)
        assert rendered[field_name] == REDACTED
        assert rendered["details"] == {"items": [{field_name: REDACTED}]}
        assert rendered["status"] == "public-diagnostic"
        assert rendered["token_type"] == "Bearer"


# Explicit security review of the mounted-file configuration contract. Do not
# derive this partition by treating every file-backed field as a secret.
_SENSITIVE_FILE_CONFIGURATION_FIELDS = frozenset(
    {
        "audit_log_secret",
        "cache_redis_url",
        "csrf_hmac_secret",
        "cwv_manual_tester_user_ids",
        "cwv_rum_signing_secret",
        "database_url",
        "elasticsearch_password",
        "idempotency_hmac_secret",
        "internal_auth_token",
        "internal_hmac_secret",
        "mfa_email_delivery_keks",
        "mfa_email_otp_hmac_keys",
        "mfa_totp_encryption_keys",
        "mfa_trusted_device_hmac_keys",
        "nats_auth_token",
        "nats_url",
        "rate_limit_storage_uri",
        "revocation_redis_url",
        "secret_key",
        "smtp_password",
        "spicedb_preshared_key",
        "spotify_client_secret",
        "spotify_oauth_state_secret",
        "spotify_token_secret",
        "storage_s3_secret_access_key",
        "token_hmac_secret",
        "vapid_private_key",
        "ws_hub_internal_secret",
    }
)
_NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS = frozenset(
    {
        "mfa_email_delivery_active_kek_id",
        "mfa_email_otp_active_hmac_key_id",
        "mfa_trusted_device_active_hmac_key_id",
        "storage_s3_access_key_id",
    }
)


def test_file_configuration_fields_have_an_explicit_redaction_disposition() -> None:
    """A mounted-file field addition requires an explicit privacy review."""
    source = Path(__file__).resolve().parents[1] / "app/core/config/base.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    declarations = [
        node
        for node in module.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_FILE_SECRET_FIELDS"
    ]
    assert len(declarations) == 1
    declaration = declarations[0].value
    assert isinstance(declaration, ast.Call)
    assert isinstance(declaration.func, ast.Name)
    assert declaration.func.id == "frozenset"
    assert len(declaration.args) == 1
    assert not declaration.keywords
    assert isinstance(declaration.args[0], ast.Set)
    inventory = ast.literal_eval(declaration.args[0])

    assert len(_SENSITIVE_FILE_CONFIGURATION_FIELDS) == 28
    assert len(_NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS) == 4
    assert _SENSITIVE_FILE_CONFIGURATION_FIELDS.isdisjoint(
        _NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS
    )
    assert inventory == (
        _SENSITIVE_FILE_CONFIGURATION_FIELDS
        | _NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS
    )


def test_file_configuration_redaction_matches_the_reviewed_partition() -> None:
    """The explicit inventory separates secrets from non-secret identifiers."""
    event = {
        **dict.fromkeys(_SENSITIVE_FILE_CONFIGURATION_FIELDS, "synthetic-value"),
        **dict.fromkeys(
            _NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS, "public-identifier"
        ),
    }

    assert _redact_pii(None, "info", event) == {
        **dict.fromkeys(_SENSITIVE_FILE_CONFIGURATION_FIELDS, REDACTED),
        **dict.fromkeys(
            _NON_SECRET_FILE_CONFIGURATION_IDENTIFIERS, "public-identifier"
        ),
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "database_url",
        "DatabaseURL",
        "database_read_replica_url",
        "databaseReadReplicaUrl",
        "cache_redis_url",
        "cache-redis-url",
        "revocation_redis_url",
        "RevocationRedisURL",
        "rate_limit_storage_uri",
        "rateLimitStorageURI",
        "nats_url",
        "NATS_URL",
        "cwv_manual_tester_user_ids",
        "cwvManualTesterUserIds",
    ],
)
def test_known_connection_and_private_cohort_fields_are_redacted_at_every_depth(
    field_name: str,
) -> None:
    """AUD-359: exact connection aliases and the private tester cohort are opaque."""
    sensitive_value = "synthetic-value"
    event = {
        field_name: sensitive_value,
        "details": [({field_name: sensitive_value},)],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: REDACTED,
        "details": [({field_name: REDACTED},)],
    }


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("url", "public-resource"),
        ("public_url", "public-resource"),
        ("cwv_deployment_url", "public-origin"),
        ("storage_s3_endpoint_url", "public-resource"),
        ("user_ids", ["public-user"]),
        ("database_url_configured", True),
        ("database_read_replica_url_configured", True),
        ("cwv_manual_tester_user_ids_count", 25),
        ("cwvManualTesterUserIdsConfigured", True),
        ("nats_url_configured", True),
    ],
    ids=[
        "url",
        "public_url",
        "cwv_deployment_url",
        "storage_s3_endpoint_url",
        "user_ids",
        "database_url_configured",
        "database_read_replica_url_configured",
        "cwv_manual_tester_user_ids_count",
        "cwvManualTesterUserIdsConfigured",
        "nats_url_configured",
    ],
)
def test_connection_alias_redaction_preserves_public_urls_users_and_metadata(
    field_name: str, field_value: Any
) -> None:
    """Do not generalize the finite aliases to every URL, user ID or metadata key."""
    event = {
        field_name: deepcopy(field_value),
        "details": [{field_name: deepcopy(field_value)}],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: field_value,
        "details": [{field_name: field_value}],
    }


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize(
    "field_name",
    [
        "databaseReadReplicaUrl",
        "nats_url",
        "cwvManualTesterUserIds",
    ],
)
def test_context_bound_connections_and_private_cohort_never_reach_renderers(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    field_name: str,
) -> None:
    """Credential-capable fields are redacted without parsing fixture values."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    context = Context()
    sensitive_value = "synthetic-value"

    try:
        logging_mod.configure_logging(json_output=json_output)
        context.run(logging_mod.bind_context, **{field_name: sensitive_value})
        logger = logging_mod.get_logger("audit-359-config-regression")
        context.run(
            logger.info,
            "connection configuration inspected",
            details={"items": [{field_name: sensitive_value}]},
            public_url="public-resource",
            user_ids=["public-user"],
        )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "connection configuration inspected" in output
    assert "public-resource" in output
    assert "public-user" in output
    assert field_name in output
    assert sensitive_value not in output
    assert output.count(REDACTED) == 2
    if json_output:
        rendered = json.loads(output)
        assert rendered[field_name] == REDACTED
        assert rendered["details"] == {"items": [{field_name: REDACTED}]}
        assert rendered["public_url"] == "public-resource"
        assert rendered["user_ids"] == ["public-user"]
