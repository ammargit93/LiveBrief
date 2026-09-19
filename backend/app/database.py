from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .settings import settings
from sqlalchemy.orm import DeclarativeBase
engine = create_async_engine( settings.DATABASE_URL, echo=False, future=True, pool_pre_ping=True )

async_session_maker = async_sessionmaker( engine, class_=AsyncSession, expire_on_commit=False )

class Base(DeclarativeBase):
    pass

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()