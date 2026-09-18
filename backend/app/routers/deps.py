import uuid
from typing import Optional
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import Workspace, ProjectSummary

async def create_workspace_with_sections(name: str, db: AsyncSession) -> Workspace:
    ws = Workspace(name=name)
    db.add(ws)
    await db.flush() # Populate the UUID id
    
    sections = [
        "Project Overview",
        "Architecture",
        "Major Features",
        "Current Decisions",
        "Known Risks",
        "Pending Decisions",
        "Open Questions",
        "Timeline"
    ]
    for sec in sections:
        db_sec = ProjectSummary(
            workspace_id=ws.id,
            section=sec,
            content=f"Initial empty template for {sec}."
        )
        db.add(db_sec)
    return ws

# Dependency: Get active workspace ID, fallback to "Default Workspace" if none specified
async def get_active_workspace_id(
    workspace_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
) -> uuid.UUID:
    if workspace_id and workspace_id not in ("None", "null", "undefined", ""):
        try:
            ws_uuid = uuid.UUID(workspace_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workspace UUID format")
            
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return ws_uuid
        
    stmt = select(Workspace).where(Workspace.name == "Default Workspace")
    res = await db.execute(stmt)
    ws = res.scalars().first()
    if not ws:
        ws = await create_workspace_with_sections("Default Workspace", db)
        await db.commit()
    return ws.id
