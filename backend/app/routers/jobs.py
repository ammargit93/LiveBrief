import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import GraphRun
from backend.app.schemas import JobResponse
from backend.app.routers.deps import get_active_workspace_id

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("", response_model=List[JobResponse])
async def get_jobs(
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(GraphRun)
        .where(GraphRun.workspace_id == workspace_id)
        .order_by(desc(GraphRun.started_at))
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{id}", response_model=JobResponse)
async def get_job(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_run = await db.get(GraphRun, id)
    if not db_run or db_run.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Job run not found in this workspace")
    return db_run
