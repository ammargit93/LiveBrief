import asyncio
import sys
import sqlalchemy as sa
from backend.app.core.database import engine, Base
from backend.app.models import * # Import all models to register them with metadata

async def init_models():
    print("Initializing database tables...")
    try:
        async with engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
            # Drop tables if we want clean state, but for production/MVP we just create if not exists
            # await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    asyncio.run(init_models())
