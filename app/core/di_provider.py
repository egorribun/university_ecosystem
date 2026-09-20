from dishka import AsyncContainer, make_async_container

from app.core.di.auth import AuthProvider
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.read_replica import READ_COMPONENT, ReadReplicaProvider
from app.core.di.search import SearchProvider
from app.core.di.spicedb import SpiceDBProvider
from app.core.di.users import UserProvider


def create_dishka_container() -> AsyncContainer:
    """Create and return the application-level dishka async container.

    Decomposed into domain-specific providers for SOLID compliance and
    improved maintainability as per TD-01 and TD-03 of the security audit.
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
        # read replica. Endpoints reach them with
        # ``Annotated[T, FromComponent(READ_COMPONENT)]``, which replaces the
        # legacy ``get_read_*`` factories in app/api/deps/services.py.
        ReadReplicaProvider(),
        UserProvider().to_component(READ_COMPONENT),
        ContentProvider().to_component(READ_COMPONENT),
    )
