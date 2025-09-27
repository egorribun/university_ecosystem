import asyncio
import uuid
from datetime import datetime

from app.core.database import async_session
from app.models.models import InviteCode


async def create_invite_code(role: str):
    code = str(uuid.uuid4()).replace("-", "")[:10].upper()
    async with async_session() as session:
        invite = InviteCode(
            code=code, role=role, is_active=True, created_at=datetime.utcnow()
        )
        session.add(invite)
        await session.commit()
        print(f"Invite code for {role}: {code}")


if __name__ == "__main__":
    role = (
        input("Для какой роли сгенерировать invite-код? (teacher/admin): ")
        .strip()
        .lower()
    )
    if role not in ("teacher", "admin"):
        print("Только teacher или admin!")
    else:
        asyncio.run(create_invite_code(role))
