import asyncio
import sys
import sqlalchemy as sa
from backend.app.core.database import engine

async def wipe_db():
    print("Wiping all rows from all database tables...")
    try:
        async with engine.begin() as conn:
            # Dynamic query to find all tables in the public schema and truncate them
            query = sa.text("""
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE;';
                    END LOOP;
                END $$;
            """)
            await conn.execute(query)
        print("All database tables wiped successfully without destroying the schema!")
    except Exception as e:
        print(f"Error wiping database: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    asyncio.run(wipe_db())
