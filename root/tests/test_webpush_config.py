import importlib
import sys

import pytest

from app.core.config import Settings, _validate_webpush_subject


@pytest.mark.parametrize(
    "value,expected",
    [
        ("mailto:Admin@example.com", "mailto:admin@example.com"),
        ("https://example.com", "https://example.com"),
        ("http://localhost:8000", "http://localhost:8000"),
    ],
)
def test_validate_webpush_subject_accepts_supported_values(value, expected):
    assert _validate_webpush_subject(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        "mailto:",  # missing address
        "mailto:not-an-email",  # missing @
        "ws://example.com",  # unsupported scheme
        "https://",  # missing host
        "http://example.com",  # insecure host
    ],
)
def test_validate_webpush_subject_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        _validate_webpush_subject(value)


def test_settings_webpush_subject_defaults(monkeypatch):
    monkeypatch.delenv("VAPID_SUBJECT", raising=False)
    settings = Settings(vapid_subject="")
    assert settings.WEBPUSH_SUBJECT == "mailto:no-reply@example.com"


def test_settings_webpush_subject_invalid(monkeypatch):
    monkeypatch.setenv("VAPID_SUBJECT", "invalid-subject")
    settings = Settings()
    with pytest.raises(ValueError):
        _ = settings.WEBPUSH_SUBJECT


def test_webpush_import_does_not_touch_database(monkeypatch):
    import app.services.push_schema as push_schema

    def _should_not_run(*_args, **_kwargs):  # pragma: no cover - safety net
        raise AssertionError("webpush import attempted to access the database")

    monkeypatch.setattr("sqlalchemy.create_engine", _should_not_run)
    monkeypatch.setattr(
        push_schema,
        "ensure_push_subscription_schema_sync",
        _should_not_run,
    )
    monkeypatch.delitem(sys.modules, "app.services.webpush", raising=False)
    module = importlib.import_module("app.services.webpush")
    assert module._Session is None


@pytest.mark.asyncio
async def test_webpush_operation_ensures_schema(monkeypatch):
    import app.services.push_schema as push_schema

    ensure_called = False

    def _fake_ensure(engine):
        nonlocal ensure_called
        ensure_called = True
        assert engine is not None

    created_engines: list[object] = []

    def _fake_create_engine(url, *args, **kwargs):
        created_engines.append((url, args, kwargs))

        class _Engine:
            pass

        return _Engine()

    sessionmaker_called = False

    class _DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):  # pragma: no cover - defensive
            return None

        def commit(self):  # pragma: no cover - defensive
            return None

    def _fake_sessionmaker(*args, **kwargs):
        nonlocal sessionmaker_called
        sessionmaker_called = True

        class _Factory:
            def __call__(self):
                return _DummySession()

        return _Factory()

    monkeypatch.setattr("sqlalchemy.create_engine", _fake_create_engine)
    monkeypatch.setattr("sqlalchemy.orm.sessionmaker", _fake_sessionmaker)
    monkeypatch.setattr(
        push_schema,
        "ensure_push_subscription_schema_sync",
        _fake_ensure,
    )
    monkeypatch.delitem(sys.modules, "app.services.webpush", raising=False)
    webpush = importlib.import_module("app.services.webpush")
    assert ensure_called is False

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *args, **kwargs):
            return _FakeResult()

    monkeypatch.setattr(webpush, "async_session", lambda: _FakeAsyncSession())

    results = await webpush.send_to_user(1, None)
    assert results == []
    assert ensure_called is True
    assert len(created_engines) == 1
    assert sessionmaker_called is True
