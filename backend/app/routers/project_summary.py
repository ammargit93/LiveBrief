import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import ProjectSummary, Timeline
from backend.app.schemas import ProjectSummaryResponse
from backend.app.routers.deps import get_active_workspace_id

router = APIRouter(prefix="/project-summary", tags=["project-summary"])

@router.get("", response_model=List[ProjectSummaryResponse])
async def get_project_summary(
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .distinct(ProjectSummary.section)
        .order_by(ProjectSummary.section, desc(ProjectSummary.version))
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/export")
async def export_project_summary(
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    from backend.app.services.export_service import export_brief_to_pdf, export_brief_to_docx
    
    section_order = [
        "Project Overview",
        "Architecture",
        "Major Features",
        "Current Decisions",
        "Known Risks",
        "Pending Decisions",
        "Open Questions",
        "Timeline"
    ]
    
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .distinct(ProjectSummary.section)
        .order_by(ProjectSummary.section, desc(ProjectSummary.version))
    )
    res = await db.execute(stmt)
    sections = res.scalars().all()
    
    sorted_sections = []
    for order_name in section_order:
        match = next((s for s in sections if s.section == order_name), None)
        if match:
            sorted_sections.append(match)
            
    for s in sections:
        if s not in sorted_sections:
            sorted_sections.append(s)

    if format == "pdf":
        pdf_stream = export_brief_to_pdf(sorted_sections)
        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="project_brief.pdf"'}
        )
    elif format == "docx":
        docx_stream = export_brief_to_docx(sorted_sections)
        return StreamingResponse(
            docx_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="project_brief.docx"'}
        )

@router.get("/{section}", response_model=ProjectSummaryResponse)
async def get_project_summary_section(
    section: str,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section)
        .order_by(desc(ProjectSummary.version))
    )
    res = await db.execute(stmt)
    db_sec = res.scalars().first()
    if not db_sec:
        raise HTTPException(status_code=404, detail=f"Section '{section}' not found in this workspace")
    return db_sec

@router.get("/{section}/history", response_model=List[ProjectSummaryResponse])
async def get_project_summary_section_history(
    section: str,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section)
        .order_by(desc(ProjectSummary.version))
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/{section}/rollback", response_model=ProjectSummaryResponse)
async def rollback_project_summary_section(
    section: str,
    version: int = Query(..., ge=1),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch the target version of the section
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section)
        .where(ProjectSummary.version == version)
    )
    res = await db.execute(stmt)
    target_summary = res.scalars().first()
    if not target_summary:
        raise HTTPException(
            status_code=404, 
            detail=f"Version {version} of section '{section}' not found in this workspace"
        )
        
    # 2. Fetch the latest version number
    stmt_latest = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section)
        .order_by(desc(ProjectSummary.version))
    )
    res_latest = await db.execute(stmt_latest)
    latest_summary = res_latest.scalars().first()
    latest_version = latest_summary.version if latest_summary else 0
    
    # 3. Create new ProjectSummary entry with incremented version
    new_summary = ProjectSummary(
        workspace_id=workspace_id,
        section=section,
        content=target_summary.content,
        version=latest_version + 1,
        updated_at=datetime.utcnow()
    )
    db.add(new_summary)
    
    # 4. Log in Timeline/Audit Trail
    db_timeline = Timeline(
        workspace_id=workspace_id,
        event=f"Brief Section '{section}' rolled back",
        reason=f"Rolled back to Version {version}",
        actor="user:rollback",
        section=section
    )
    db.add(db_timeline)
    
    await db.commit()
    await db.refresh(new_summary)
    return new_summary

