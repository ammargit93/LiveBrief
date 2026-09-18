import sys
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
root_logger = logging.getLogger()
if not root_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)

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
            
    # Startup recovery mechanism for incomplete pipeline runs
    try:
        import asyncio
        from sqlalchemy import or_
        from backend.app.models import GraphRun
        from backend.app.services.agent_service import run_agent_pipeline
        
        async with async_session_maker() as db:
            stmt = select(GraphRun).where(or_(GraphRun.status == "running", GraphRun.status == "interrupted/recoverable"))
            res = await db.execute(stmt)
            incomplete_runs = res.scalars().all()
            
            if incomplete_runs:
                logger.info(f"Startup recovery: Found {len(incomplete_runs)} incomplete runs to recover.")
                for run in incomplete_runs:
                    logger.info(f"Recovering GraphRun {run.id} (node: {run.current_node}, status: {run.status})")
                    run.status = "interrupted/recoverable"
                    run.error = "Interrupted due to backend restart."
                    asyncio.create_task(run_agent_pipeline(str(run.id)))
                await db.commit()
    except Exception as recovery_err:
        logger.error(f"Startup recovery failed: {recovery_err}")
        
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
