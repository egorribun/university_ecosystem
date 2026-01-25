import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.users import User


async def verify_user_decomposition():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Test creation via proxies/init
        new_user = User(
            email="test_decomp@example.com",
            hashed_password="...",
            institute="Institute of Technology",
            about="I am a test student",
            program="Computer Science",
            telegram="@testuser",
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        print(f"Created User ID: {new_user.id}")
        print(f"Institute (via proxy): {new_user.institute}")
        print(f"About (via proxy): {new_user.about}")
        print(f"Telegram (via proxy): {new_user.telegram}")
        print(f"Program (via proxy): {new_user.program}")

        # Basic assertions
        assert new_user.institute == "Institute of Technology"
        assert new_user.about == "I am a test student"
        assert new_user.program == "Computer Science"
        assert new_user.telegram == "@testuser"

        print("Verification successful!")


if __name__ == "__main__":
    asyncio.run(verify_user_decomposition())
