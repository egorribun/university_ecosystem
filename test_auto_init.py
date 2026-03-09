import sys
import os
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

# Set dummy env vars for Settings load
os.environ['DATABASE_URL']='sqlite+aiosqlite:///./test_auto.db'
os.environ['SECRET_KEY']='test-secret-key-32-characters-long-entropy'

from app.core.database import engine

async def test_auto_init():
    print(f"Engine before access: {engine}")
    # This should trigger auto-init
    print(f"Dialect: {engine.dialect.name}")
    print(f"Engine after access: {engine}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_auto_init())
