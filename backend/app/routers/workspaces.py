import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import Workspace
from backend.app.routers.deps import create_workspace_with_sections

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

# Pydantic schemas for workspaces
class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

@router.get("", response_model=List[WorkspaceResponse])
async def get_workspaces(db: AsyncSession = Depends(get_db)):
    stmt = select(Workspace).order_by(Workspace.name)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("", response_model=WorkspaceResponse)
async def create_workspace(data: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(Workspace).where(Workspace.name == data.name)
    res = await db.execute(stmt)
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Workspace name already exists")
    ws = await create_workspace_with_sections(data.name, db)
    await db.commit()
    return ws
