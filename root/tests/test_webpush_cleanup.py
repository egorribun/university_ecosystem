import pytest

from app.services import webpush as webpush_module


@pytest.mark.anyio
async def test_webpush_cleanup_allows_repeated_startup(monkeypatch: pytest.MonkeyPatch):
    create_calls = 0
    dispose_calls = 0
    close_calls = 0

    class _DummyEngine:
        def dispose(self) -> None:
            nonlocal dispose_calls
            dispose_calls += 1

    class _DummySessionmaker:
        def close_all(self) -> None:
            nonlocal close_calls
            close_calls += 1

    def _fake_create_engine(*args, **kwargs):
        nonlocal create_calls
        create_calls += 1
        return _DummyEngine()

    def _fake_sessionmaker(*args, **kwargs):
        return _DummySessionmaker()

    monkeypatch.setattr(webpush_module, "_sync_engine", None)
    monkeypatch.setattr(webpush_module, "_Session", None)
    monkeypatch.setattr(webpush_module, "create_engine", _fake_create_engine)
    monkeypatch.setattr(webpush_module, "sessionmaker", _fake_sessionmaker)
    monkeypatch.setattr(
        webpush_module.push_schema,
        "ensure_push_subscription_schema_sync",
        lambda engine: None,
    )

    await webpush_module._ensure_async_sessionmaker()
    assert create_calls == 1
    assert webpush_module._sync_engine is not None
    assert webpush_module._Session is not None

    webpush_module.cleanup()
    assert dispose_calls == 1
    assert close_calls == 1
    assert webpush_module._sync_engine is None
    assert webpush_module._Session is None

    await webpush_module._ensure_async_sessionmaker()
    assert create_calls == 2
    assert webpush_module._sync_engine is not None
    assert webpush_module._Session is not None

    webpush_module.cleanup()
    assert dispose_calls == 2
    assert close_calls == 2
    assert webpush_module._sync_engine is None
    assert webpush_module._Session is None
