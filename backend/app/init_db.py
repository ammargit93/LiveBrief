import asyncio
import sys
from backend.app.database import engine, Base
from backend.app.models import * # Import all models to register them with metadata

async def init_models():
    print("Initializing database tables...")
    try:
        async with engine.begin() as conn:
            # Drop tables if we want clean state, but for production/MVP we just create if not exists
            # await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    asyncio.run(init_models())
