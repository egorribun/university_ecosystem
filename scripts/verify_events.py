import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Set default environment variables for local execution if not present
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-key-32-characters-long-entropy"
)  # pragma: allowlist secret
os.environ.setdefault("ENVIRONMENT", "local")

from sqlalchemy.future import select  # noqa: E402

from app.core.database import Base, async_session, engine, init_database  # noqa: E402
from app.core.events import UserCreated, register_event_listeners  # noqa: E402
from app.models.domain_events import StoredEvent  # noqa: E402
from app.models.users import User  # noqa: E402


async def verify_event_capture():
    # 0. Ensure tables exist (for SQLite/local)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 1. Register listeners
    register_event_listeners()

    print("Testing domain event capture...")

    async with async_session() as session:
        # Create a test user
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            email=test_email,
            hashed_password="hashed_password",  # pragma: allowlist secret  # noqa: S106
            profile={"full_name": "Event Test User"},
            is_active=True,
        )

        # 2. Record a domain event
        user.record_event(UserCreated(user_id=1, email=test_email))

        session.add(user)
        # Flush to trigger the listener
        await session.flush()
        # Commit to save everything
        await session.commit()

        print(f"User created: {test_email}")

    # 3. Verify event persistence
    async with async_session() as session:
        stmt = (
            select(StoredEvent)
            .where(StoredEvent.aggregate_type == "User")
            .order_by(StoredEvent.created_at.desc())
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        found = False
        for e in events:
            if e.payload.get("email") == test_email:
                print("SUCCESS: Domain event captured and persisted!")
                print(f"Event ID: {e.id}, Type: {e.event_type}, Payload: {e.payload}")
                found = True
                break

        if not found:
            print("FAILURE: Domain event not found in storage.")


if __name__ == "__main__":
    import os

    # Override DATABASE_URL for local connection if needed
    if "postgres" in os.environ.get("DATABASE_URL", ""):
        os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].replace(
            "@postgres:", "@localhost:"
        )

    # Initialize database engines
    init_database()

    asyncio.run(verify_event_capture())
