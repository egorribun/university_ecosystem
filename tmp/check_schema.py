import asyncio

from sqlalchemy import inspect

from app.core.database import engine


async def check_schema():
    async with engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("push_subscriptions")
        )
        print([c["name"] for c in columns])


if __name__ == "__main__":
    asyncio.run(check_schema())
