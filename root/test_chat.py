import asyncio
import sys
sys.path.insert(0, '.')

from app.core.database import async_session
from app.models.chat import Chat
from app.models.models import User

async def test_create_chat():
    async with async_session() as session:
        # Get first two users
        from sqlalchemy import select
        result = await session.execute(select(User).limit(2))
        users = result.scalars().all()
        
        if len(users) < 2:
            print("Not enough users in database")
            return
            
        user1 = users[0]
        user2 = users[1]
        
        print(f"User 1: {user1.id} ({type(user1.id)})")
        print(f"User 2: {user2.id} ({type(user2.id)})")
        
        # Try to create a chat
        new_chat = Chat()
        new_chat.participants.append(user1)
        new_chat.participants.append(user2)
        session.add(new_chat)
        
        try:
            await session.commit()
            print("SUCCESS: Chat created!")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test_create_chat())
