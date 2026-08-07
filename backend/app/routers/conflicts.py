import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import Conflict
from backend.app.schemas import ConflictResponse
from backend.app.routers.deps import get_active_workspace_id

router = APIRouter(prefix="/conflicts", tags=["conflicts"])

@router.get("", response_model=List[ConflictResponse])
async def get_conflicts(
    resolved: Optional[bool] = None,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Conflict)
        .where(Conflict.workspace_id == workspace_id)
        .order_by(desc(Conflict.created_at))
        .limit(limit)
        .offset(offset)
    )
    if resolved is not None:
        stmt = stmt.where(Conflict.resolved == resolved)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{id}", response_model=ConflictResponse)
async def get_conflict(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_conflict = await db.get(Conflict, id)
    if not db_conflict or db_conflict.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Conflict not found in this workspace")
    return db_conflict
