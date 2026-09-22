from collections.abc import Sequence

from dishka import AsyncContainer, Provider, make_async_container

from app.core.di.auth import AuthProvider
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.read_replica import READ_COMPONENT, ReadReplicaProvider
from app.core.di.search import SearchProvider
from app.core.di.spicedb import SpiceDBProvider
from app.core.di.users import UserProvider


def create_dishka_container(
    overrides: Sequence[Provider] = (),
) -> AsyncContainer:
    """Create and return the application-level dishka async container.

    Decomposed into domain-specific providers for SOLID compliance and
    improved maintainability as per TD-01 and TD-03 of the security audit.

    ``overrides`` are registered last so they take precedence over the
    application providers.  This exists for the test suite: once an endpoint
    asks for ``FromDishka[AsyncDatabaseSession]`` it no longer consults
    FastAPI's ``dependency_overrides``, so rebinding the container is the only
    way to keep a test's session identity across a request.  Production calls
    pass nothing.
    """
    return make_async_container(
        InfrastructureProvider(),
        AuthProvider(),
        SpiceDBProvider(),  # TD-14-05: singleton gRPC channel + REQUEST-scoped PermissionChecker
        UserProvider(),
        ContentProvider(),
        ChatProvider(),
        CQRSProvider(),
        SearchProvider(),
        # BE-04: the same query services registered a second time against the
        # read replica.  An endpoint reaches them with
        # ``Annotated[T, FromComponent(READ_COMPONENT)]``; this is what replaced
        # the ``get_read_*`` half of the 43 deleted legacy factories.
        ReadReplicaProvider(),
        UserProvider().to_component(READ_COMPONENT),
        ContentProvider().to_component(READ_COMPONENT),
        # Chat and CQRS cover the rest of the read-replica surface: the chat
        # query service and the stats and schedule query handlers.  Neither
        # needs extra bridging -- their dependencies resolve inside the
        # component off ReadReplicaProvider's session, which
        # tests/test_di_container.py verifies.
        ChatProvider().to_component(READ_COMPONENT),
        CQRSProvider().to_component(READ_COMPONENT),
        # Last registration wins in dishka, so overrides go at the end.
        *overrides,
    )
