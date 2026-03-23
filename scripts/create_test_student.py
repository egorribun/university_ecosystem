import asyncio
import os
import secrets  # LOW-W19: used for secure fallback password generation
import sys
from pathlib import Path

# LOW-W19: use script location instead of fragile os.getcwd()
sys.path.insert(0, str(Path(__file__).parent.parent))

from dishka import Scope, make_async_container

from app.core.database import init_database
from app.core.di_provider import AppProvider
from app.models.enums import UserRole
from app.schemas import schemas
from app.services.user_service import UserService


async def create_student():
    # Initialize database engines and proxies
    init_database()

    # Initialize the Dishka container
    container = make_async_container(AppProvider())

    # Use a request-scoped container to resolve dependencies (db session, repositories, etc.)
    async with container(scope=Scope.REQUEST) as request_container:
        user_service = await request_container.get(UserService)

        user_in = schemas.UserCreate(
            email="student@example.com",
            # LOW-W19: avoid hardcoded password; read from env or generate a secure random value
            password=os.environ.get("TEST_PASSWORD", secrets.token_urlsafe(16)),
            full_name="Test Student",
            role=UserRole.STUDENT,
            about="I am a test student user created for verification.",
            telegram="@teststudent",
            institute="Information Technology",
            course="3",
            education_level="Bachelor",
            track="Software Engineering",
            program="Computer Science",
            record_book_number="ST-12345",
        )

        try:
            # register_user handles password hashing and related entity creation (profile/edu)
            user = await user_service.register_user(user_in)
            print(f"Successfully created student user: {user.email} (ID: {user.id})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("User student@example.com already exists.")
            else:
                print(f"Failed to create user: {e}")
                import traceback

                traceback.print_exc()

    await container.close()


if __name__ == "__main__":
    asyncio.run(create_student())
