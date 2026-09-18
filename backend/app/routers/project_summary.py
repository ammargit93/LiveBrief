import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import ProjectSummary
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
        .order_by(ProjectSummary.section, desc(ProjectSummary.updated_at))
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
        .order_by(ProjectSummary.section, desc(ProjectSummary.updated_at))
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
        .order_by(desc(ProjectSummary.updated_at))
    )
    res = await db.execute(stmt)
    db_sec = res.scalars().first()
    if not db_sec:
        raise HTTPException(status_code=404, detail=f"Section '{section}' not found in this workspace")
    return db_sec

