from dishka import AsyncContainer, make_async_container

from app.core.di.auth import AuthProvider
from app.core.di.chat import ChatProvider
from app.core.di.content import ContentProvider
from app.core.di.cqrs import CQRSProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.di.users import UserProvider


def create_dishka_container() -> AsyncContainer:
    """Create and return the application-level dishka async container.
    
    Decomposed into domain-specific providers for SOLID compliance and
    improved maintainability as per TD-01 and TD-03 of the security audit.
    """
    return make_async_container(
        InfrastructureProvider(),
        AuthProvider(),
        UserProvider(),
        ContentProvider(),
        ChatProvider(),
        CQRSProvider(),
    )
