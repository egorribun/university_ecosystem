"""
Tests for API validation helpers.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given
from hypothesis import settings as hypo_settings
from hypothesis import strategies as st

from app.api.validation import (
    ensure_exists,
    raise_conflict,
    raise_forbidden,
    raise_http_error,
    raise_not_found,
    raise_unauthorized,
    raise_validation_error,
    require_admin,
    require_owner_or_admin,
    require_teacher_or_admin,
)
from app.models.enums import UserRole


class TestRaiseNotFound:
    """Tests for raise_not_found helper."""

    def test_raises_404_with_correct_status(self):
        """Should raise HTTPException with 404 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("news", "ru")

        assert exc_info.value.status_code == 404

    def test_includes_resource_key_in_detail(self):
        """Should include translated message in detail."""
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("events", "en")

        # Should have some detail message
        assert exc_info.value.detail is not None


class TestRaiseForbidden:
    """Tests for raise_forbidden helper."""

    def test_raises_403_status(self):
        """Should raise HTTPException with 403 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden("ru")

        assert exc_info.value.status_code == 403


class TestRaiseValidationError:
    """Tests for raise_validation_error helper."""

    def test_raises_400_status(self):
        """Should raise HTTPException with 400 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_validation_error("errors.validation.required", "ru")

        assert exc_info.value.status_code == 400


class TestRaiseConflict:
    """Tests for raise_conflict helper."""

    def test_raises_409_status(self):
        """Should raise HTTPException with 409 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_conflict("errors.events.registration_closed", "ru")

        assert exc_info.value.status_code == 409


class TestRequireAdmin:
    """Tests for require_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.role = "admin"

        # Should not raise
        require_admin(user, "ru")

    def test_raises_for_non_admin(self):
        """Should raise 403 for non-admin user."""
        user = MagicMock()
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_admin(user, "ru")

        assert exc_info.value.status_code == 403


class TestRequireTeacherOrAdmin:
    """Tests for require_teacher_or_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.role = "admin"

        require_teacher_or_admin(user, "ru")

    def test_passes_for_teacher(self):
        """Should not raise for teacher user."""
        user = MagicMock()
        user.role = "teacher"

        require_teacher_or_admin(user, "ru")

    def test_raises_for_student(self):
        """Should raise 403 for student user."""
        user = MagicMock()
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_teacher_or_admin(user, "ru")

        assert exc_info.value.status_code == 403


class TestRequireOwnerOrAdmin:
    """Tests for require_owner_or_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.id = 1
        user.role = "admin"

        require_owner_or_admin(user, "ru", owner_id=99)

    def test_passes_for_owner(self):
        """Should not raise for resource owner."""
        user = MagicMock()
        user.id = 42
        user.role = "student"

        require_owner_or_admin(user, "ru", owner_id=42)

    def test_raises_for_non_owner_non_admin(self):
        """Should raise 403 for non-owner non-admin."""
        user = MagicMock()
        user.id = 1
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_owner_or_admin(user, "ru", owner_id=99)

        assert exc_info.value.status_code == 403

    def test_passes_for_teacher_when_allowed(self):
        """Should not raise for teacher when allow_teacher=True."""
        user = MagicMock()
        user.id = 1
        user.role = "teacher"

        require_owner_or_admin(user, "ru", owner_id=99, allow_teacher=True)


class TestEnsureExists:
    """Tests for ensure_exists helper."""

    def test_returns_resource_if_exists(self):
        """Should return resource when not None."""
        resource = {"id": 1, "name": "test"}

        result = ensure_exists(resource, "news", "ru")

        assert result == resource

    def test_raises_404_if_none(self):
        """Should raise 404 when resource is None."""
        with pytest.raises(HTTPException) as exc_info:
            ensure_exists(None, "news", "ru")

        assert exc_info.value.status_code == 404


# ── Property-based tests ─────────────────────────────────────────────────────
#
# These tests assert that validation helpers preserve their core invariants
# (status code, exception type, return shape) under adversarial input. The
# strategies feed arbitrary unicode strings, including null bytes, control
# characters, RTL marks, and surrogate pairs, to confirm that helpers never
# crash with an unexpected exception type and never accidentally return
# instead of raising.

# A "harmless" message key — we don't care about the actual translation, only
# that helpers tolerate it. Bounded length keeps Hypothesis fast.
_message_key_st = st.text(min_size=0, max_size=80)

# Locale strings — both well-formed (en, ru, en-US) and adversarial garbage.
# DEFAULT_LOCALE fallback must absorb everything without raising.
_locale_st = st.one_of(
    st.sampled_from(["en", "ru", "en-US", "ru-RU", "fr", "de"]),
    # Unicode garbage — \x00, RTL marks, surrogates are exercised here. We
    # blacklist the surrogate category to keep `text.format()` from raising
    # `UnicodeEncodeError` during interpolation (Python's str.format() refuses
    # lone surrogates). Surrogate-pair behaviour is covered by the dedicated
    # test below.
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=0,
        max_size=24,
    ),
    st.just(""),
)

# Resource keys — non-empty so the auto-built `errors.<key>.not_found` path
# stays exercised. We exclude characters that would make the key embed control
# bytes; `translate()` will fall back to the key itself when no entry matches.
_resource_key_st = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"),
        blacklist_characters="{}",
    ),
    min_size=1,
    max_size=40,
)


def _make_user(role: UserRole, user_id: int = 1) -> MagicMock:
    """Construct a User-shaped mock with a ``role`` and ``id``."""
    user = MagicMock()
    user.role = role
    user.id = user_id
    return user


# ── 1. raise_http_error: status code passes through unchanged ────────────────


@hypo_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    status_code=st.integers(min_value=400, max_value=599),
    message_key=_message_key_st,
    locale=_locale_st,
)
def test_raise_http_error_preserves_status_code(
    status_code: int, message_key: str, locale: str
) -> None:
    """The raised HTTPException carries the exact status_code we passed in."""
    with pytest.raises(HTTPException) as exc_info:
        raise_http_error(status_code, message_key, locale)
    assert exc_info.value.status_code == status_code


@hypo_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    status_code=st.integers(min_value=400, max_value=599),
    message_key=_message_key_st,
    locale=_locale_st,
    headers=st.dictionaries(
        keys=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="-_"
            ),
            min_size=1,
            max_size=20,
        ),
        values=st.text(
            alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
            min_size=0,
            max_size=40,
        ),
        max_size=5,
    ),
)
def test_raise_http_error_passes_headers_through(
    status_code: int,
    message_key: str,
    locale: str,
    headers: dict[str, str],
) -> None:
    """Arbitrary header dicts are preserved verbatim on the raised exception."""
    with pytest.raises(HTTPException) as exc_info:
        raise_http_error(status_code, message_key, locale, headers=headers)
    assert exc_info.value.headers == headers


# ── 2. Each typed raise_* helper pins its status code ────────────────────────


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(resource_key=_resource_key_st, locale=_locale_st)
def test_raise_not_found_always_404(resource_key: str, locale: str) -> None:
    """``raise_not_found`` raises HTTP 404 regardless of input shape."""
    with pytest.raises(HTTPException) as exc_info:
        raise_not_found(resource_key, locale)
    assert exc_info.value.status_code == 404


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    resource_key=_resource_key_st,
    locale=_locale_st,
    resource_id=st.one_of(
        st.uuids(),
        st.integers(min_value=-(2**31), max_value=2**31),
        st.text(max_size=30),
        st.none(),
    ),
)
def test_raise_not_found_accepts_any_resource_id_shape(
    resource_key: str,
    locale: str,
    resource_id: uuid.UUID | int | str | None,
) -> None:
    """``resource_id`` is purely informational — any UUID/int/str/None works."""
    with pytest.raises(HTTPException) as exc_info:
        raise_not_found(resource_key, locale, resource_id=resource_id)
    assert exc_info.value.status_code == 404


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    resource_key=_resource_key_st,
    locale=_locale_st,
    exact_key=_message_key_st,
)
def test_raise_not_found_exact_key_override(
    resource_key: str, locale: str, exact_key: str
) -> None:
    """``exact_key`` override never alters the 404 status code."""
    with pytest.raises(HTTPException) as exc_info:
        raise_not_found(resource_key, locale, exact_key=exact_key)
    assert exc_info.value.status_code == 404


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(locale=_locale_st, message_key=_message_key_st)
def test_raise_forbidden_always_403(locale: str, message_key: str) -> None:
    """``raise_forbidden`` raises HTTP 403 regardless of message key."""
    with pytest.raises(HTTPException) as exc_info:
        raise_forbidden(locale, message_key)
    assert exc_info.value.status_code == 403


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(locale=_locale_st, message_key=_message_key_st)
def test_raise_unauthorized_always_401(locale: str, message_key: str) -> None:
    """``raise_unauthorized`` raises HTTP 401 regardless of message key."""
    with pytest.raises(HTTPException) as exc_info:
        raise_unauthorized(locale, message_key)
    assert exc_info.value.status_code == 401


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(locale=_locale_st, message_key=_message_key_st)
def test_raise_unauthorized_includes_www_authenticate_header(
    locale: str, message_key: str
) -> None:
    """When supplied, WWW-Authenticate-style headers reach the exception."""
    headers = {"WWW-Authenticate": "Bearer"}
    with pytest.raises(HTTPException) as exc_info:
        raise_unauthorized(locale, message_key, headers=headers)
    assert exc_info.value.headers == headers


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(message_key=_message_key_st, locale=_locale_st)
def test_raise_validation_error_always_400(message_key: str, locale: str) -> None:
    """``raise_validation_error`` raises HTTP 400 regardless of message key."""
    with pytest.raises(HTTPException) as exc_info:
        raise_validation_error(message_key, locale)
    assert exc_info.value.status_code == 400


@hypo_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(message_key=_message_key_st, locale=_locale_st)
def test_raise_conflict_always_409(message_key: str, locale: str) -> None:
    """``raise_conflict`` raises HTTP 409 regardless of message key."""
    with pytest.raises(HTTPException) as exc_info:
        raise_conflict(message_key, locale)
    assert exc_info.value.status_code == 409


# ── 3. kwargs interpolation never crashes ────────────────────────────────────
#
# The localization layer falls back to the un-interpolated text on KeyError;
# we confirm that arbitrary kwargs (including unused ones) never escape as
# anything other than HTTPException.


# Message keys without curly braces — `translate()` invokes `str.format()` for
# kwargs interpolation and only suppresses ``KeyError``; a stray ``{`` or ``}``
# would surface as ``ValueError`` from format(). We deliberately keep adversarial
# format strings out of *this* property (which is about kwargs tolerance) so it
# stays meaningful; format-string brittleness is a separate concern.
_message_key_no_braces_st = st.text(
    alphabet=st.characters(blacklist_characters="{}"),
    min_size=0,
    max_size=80,
)


@hypo_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    message_key=_message_key_no_braces_st,
    locale=_locale_st,
    extra_kwargs=st.dictionaries(
        keys=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=1,
            max_size=10,
        ).filter(lambda s: s.isidentifier()),
        values=st.one_of(st.text(max_size=20), st.integers(), st.booleans()),
        max_size=4,
    ),
)
def test_raise_validation_error_tolerates_arbitrary_kwargs(
    message_key: str, locale: str, extra_kwargs: dict[str, object]
) -> None:
    """Unused kwargs propagate to ``translate()`` without raising."""
    with pytest.raises(HTTPException):
        raise_validation_error(message_key, locale, **extra_kwargs)


# ── 4. Surrogate pairs and null bytes do not crash helpers ───────────────────
#
# Lone surrogates would normally trip Python's str.format(); the localization
# layer guards interpolation behind a try/except, so the public API stays
# safe. Null bytes pass through to the detail message — also safe.


@hypo_settings(max_examples=20)
@given(
    locale=st.text(
        alphabet=st.characters(whitelist_categories=("Cs",)),
        min_size=1,
        max_size=4,
    ),
)
def test_helpers_tolerate_surrogate_locale(locale: str) -> None:
    """Lone surrogates in the locale string do not propagate as errors."""
    with pytest.raises(HTTPException) as exc_info:
        raise_not_found("news", locale)
    assert exc_info.value.status_code == 404


def test_helpers_tolerate_null_byte_in_message_key() -> None:
    """A null byte in the message key reaches the detail without crashing."""
    with pytest.raises(HTTPException) as exc_info:
        raise_validation_error("errors.\x00.invalid", "en")
    assert exc_info.value.status_code == 400


def test_helpers_tolerate_very_long_message_key() -> None:
    """An extremely long message key is handled (falls back to the key itself)."""
    very_long = "x" * 10_000
    with pytest.raises(HTTPException) as exc_info:
        raise_validation_error(very_long, "en")
    assert exc_info.value.status_code == 400


# ── 5. Role checks: cover the entire UserRole enum ───────────────────────────


@hypo_settings(max_examples=20)
@given(role=st.sampled_from(list(UserRole)))
def test_require_admin_only_admin_passes(role: UserRole) -> None:
    """Only ``UserRole.ADMIN`` may pass ``require_admin``."""
    user = _make_user(role)
    if role == UserRole.ADMIN:
        require_admin(user, "en")  # must not raise
    else:
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user, "en")
        assert exc_info.value.status_code == 403


@hypo_settings(max_examples=20)
@given(role=st.sampled_from(list(UserRole)))
def test_require_teacher_or_admin_only_those_two_pass(role: UserRole) -> None:
    """Only ``ADMIN`` and ``TEACHER`` may pass ``require_teacher_or_admin``."""
    user = _make_user(role)
    if role in (UserRole.ADMIN, UserRole.TEACHER):
        require_teacher_or_admin(user, "en")  # must not raise
    else:
        with pytest.raises(HTTPException) as exc_info:
            require_teacher_or_admin(user, "en")
        assert exc_info.value.status_code == 403


# ── 6. Owner-or-admin: covers role × ownership matrix ────────────────────────


@hypo_settings(max_examples=30)
@given(
    role=st.sampled_from(list(UserRole)),
    is_owner=st.booleans(),
    allow_teacher=st.booleans(),
)
def test_require_owner_or_admin_matrix(
    role: UserRole, is_owner: bool, allow_teacher: bool
) -> None:
    """Pass if admin OR (allow_teacher and teacher) OR owner; else 403."""
    user_id = 42
    owner_id = user_id if is_owner else 99

    user = _make_user(role, user_id=user_id)

    should_pass = (
        role == UserRole.ADMIN
        or (allow_teacher and role == UserRole.TEACHER)
        or is_owner
    )

    if should_pass:
        require_owner_or_admin(
            user, "en", owner_id=owner_id, allow_teacher=allow_teacher
        )
    else:
        with pytest.raises(HTTPException) as exc_info:
            require_owner_or_admin(
                user, "en", owner_id=owner_id, allow_teacher=allow_teacher
            )
        assert exc_info.value.status_code == 403


@hypo_settings(max_examples=20)
@given(
    owner_id=st.one_of(
        st.uuids(),
        st.integers(min_value=-(2**31), max_value=2**31),
        st.text(min_size=1, max_size=20),
    ),
)
def test_require_owner_or_admin_owner_id_typing(
    owner_id: uuid.UUID | int | str,
) -> None:
    """``owner_id`` accepts UUID / int / str — the owner branch must pass."""
    user = _make_user(UserRole.STUDENT, user_id=owner_id)
    require_owner_or_admin(user, "en", owner_id=owner_id)


# ── 7. ensure_exists: identity for non-None, 404 for None ────────────────────


@hypo_settings(max_examples=50)
@given(
    resource=st.one_of(
        st.text(min_size=1, max_size=20),
        st.integers(),
        st.lists(st.integers(), max_size=5),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=5),
            values=st.integers(),
            max_size=3,
        ),
        st.uuids(),
        st.booleans(),
    ),
    resource_key=_resource_key_st,
    locale=_locale_st,
)
def test_ensure_exists_returns_non_none_unchanged(
    resource: object, resource_key: str, locale: str
) -> None:
    """For any non-None ``resource``, ``ensure_exists`` returns it as-is."""
    assert ensure_exists(resource, resource_key, locale) is resource


@hypo_settings(max_examples=20)
@given(resource_key=_resource_key_st, locale=_locale_st)
def test_ensure_exists_none_always_raises_404(resource_key: str, locale: str) -> None:
    """``ensure_exists(None, ...)`` always raises HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        ensure_exists(None, resource_key, locale)
    assert exc_info.value.status_code == 404


# Falsy-but-not-None values (0, "", [], False) must still pass through —
# documenting that ``ensure_exists`` discriminates by `is None`, not truthiness.
@pytest.mark.parametrize("falsy", [0, 0.0, "", [], {}, False])
def test_ensure_exists_distinguishes_none_from_falsy(falsy: object) -> None:
    """Falsy values are not treated as 'missing'; only ``None`` raises."""
    assert ensure_exists(falsy, "news", "en") is falsy
