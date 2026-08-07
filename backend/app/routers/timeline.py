import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import Timeline
from backend.app.schemas import TimelineResponse
from backend.app.routers.deps import get_active_workspace_id

router = APIRouter(prefix="/timeline", tags=["timeline"])

@router.get("", response_model=List[TimelineResponse])
async def get_timeline(
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Timeline)
        .where(Timeline.workspace_id == workspace_id)
        .order_by(desc(Timeline.timestamp))
    )
    res = await db.execute(stmt)
    return res.scalars().all()
