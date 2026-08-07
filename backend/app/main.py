import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import async_session_maker
from backend.app.models import Workspace
from backend.app.routers import api_router
from backend.app.routers.deps import create_workspace_with_sections

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-seed the Default Workspace on startup if it does not exist
    async with async_session_maker() as db:
        stmt = select(Workspace).where(Workspace.name == "Default Workspace")
        res = await db.execute(stmt)
        ws = res.scalars().first()
        if not ws:
            logger.info("Seeding Default Workspace with initial sections...")
            await create_workspace_with_sections("Default Workspace", db)
            await db.commit()
    yield

app = FastAPI(
    title="LiveBrief API",
    description="Interactive backend service compiling living briefs from software project documents.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(api_router)
