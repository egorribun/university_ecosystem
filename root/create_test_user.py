"""Quick script to create a test admin user for local development."""

import asyncio
import os
import sys

# Fix for Windows: psycopg requires SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add the root directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.database import Base, async_session, engine
from app.models.models import User


async def create_test_admin():
    """Create a test admin user if not exists."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == "admin@example.com"))
        existing = result.scalar_one_or_none()

        if existing:
            # Reset password in case it was changed
            existing.hashed_password = get_password_hash("admin123")
            await db.commit()
            print(f"Admin user already exists with ID: {existing.id}")
            print("Password has been reset to: admin123")
            return existing

        # Create admin user
        admin = User(
            email="admin@example.com",
            hashed_password=get_password_hash("admin123"),
            full_name="Test Admin",
            role="admin",
            is_active=True,
            mfa_required=False,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        print("Created admin user:")
        print("  Email: admin@example.com")
        print("  Password: admin123")
        print(f"  ID: {admin.id}")

        return admin


if __name__ == "__main__":
    asyncio.run(create_test_admin())
