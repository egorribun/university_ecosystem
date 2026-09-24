"""The application container registers every domain provider exactly once."""

from __future__ import annotations

from unittest.mock import patch

from dishka import Provider

from app.core.di.read_replica import READ_COMPONENT
from app.core.di_provider import create_dishka_container


def test_container_registers_domain_and_read_replica_providers_then_overrides() -> None:
    override = Provider()
    with patch("app.core.di_provider.make_async_container") as make:
        create_dishka_container([override])

    make.assert_called_once()
    providers = make.call_args.args
    assert [type(provider).__name__ for provider in providers[:9]] == [
        "InfrastructureProvider",
        "AuthProvider",
        "SpiceDBProvider",
        "UserProvider",
        "ContentProvider",
        "ChatProvider",
        "CQRSProvider",
        "SearchProvider",
        "ReadReplicaProvider",
    ]
    assert [provider.component for provider in providers[:8]] == [""] * 8
    # The read replica re-registers the user, content, chat and CQRS services.
    read_side = providers[9:13]
    assert [provider.component for provider in read_side] == [READ_COMPONENT] * 4
    assert [_provided(provider) for provider in read_side] == [
        _provided(providers[index]) for index in (3, 4, 5, 6)
    ]
    # Last registration wins in dishka, so test overrides must come last.
    assert len(providers) == 14
    assert providers[-1] is override


def _provided(provider: object) -> list[str]:
    return sorted(
        str(factory.provides.type_hint)
        for factory in provider.factories  # type: ignore[attr-defined]
    )
