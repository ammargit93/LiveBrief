import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.database import get_db, async_session_maker
from backend.app.models import Document, GraphRun, ProjectSummary, Review, Conflict, Timeline, Workspace
from backend.app.schemas import (
    DocumentResponse, ConflictResponse, ProjectSummaryResponse, 
    ReviewResponse, RejectRequest, TimelineResponse, JobResponse
)
from backend.app.agent import run_agent_pipeline

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

# Helper to build a workspace and pre-seed its 8 brief sections
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
            content=f"Initial empty template for {sec}.",
            version=1
        )
        db.add(db_sec)
    return ws

# Dependency: Get active workspace ID, fallback to "Default Workspace" if none specified
async def get_active_workspace_id(
    workspace_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
) -> uuid.UUID:
    if workspace_id:
        ws = await db.get(Workspace, workspace_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace_id
        
    stmt = select(Workspace).where(Workspace.name == "Default Workspace")
    res = await db.execute(stmt)
    ws = res.scalars().first()
    if not ws:
        ws = await create_workspace_with_sections("Default Workspace", db)
        await db.commit()
    return ws.id

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

# Pydantic schemas for workspaces
class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    class Config:
        from_attributes = True

# ----------------- WORKSPACE ENDPOINTS -----------------

@app.get("/workspaces", response_model=List[WorkspaceResponse])
async def get_workspaces(db: AsyncSession = Depends(get_db)):
    stmt = select(Workspace).order_by(Workspace.name)
    res = await db.execute(stmt)
    return res.scalars().all()

@app.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(data: WorkspaceCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(Workspace).where(Workspace.name == data.name)
    res = await db.execute(stmt)
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Workspace name already exists")
    ws = await create_workspace_with_sections(data.name, db)
    await db.commit()
    return ws

# ----------------- DOCUMENT INGESTION & TRACKING -----------------

@app.post("/documents/upload", response_model=List[DocumentResponse])
async def upload_documents(
    files: List[UploadFile] = File(...),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    upload_dir = settings.STORAGE_PATH
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_docs = []
    batch_id = uuid.uuid4()
    
    for upload_file in files:
        filename = upload_file.filename
        storage_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{filename}")
        
        # Stream the upload in 1MB chunks to disk
        try:
            with open(storage_path, "wb") as f:
                while chunk := await upload_file.read(1024 * 1024):
                    f.write(chunk)
        except Exception as e:
            logger.error(f"Failed to save file {filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")
            
        # Versioning: check if filename exists in this workspace
        stmt = (
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .where(Document.filename == filename)
            .order_by(desc(Document.version))
        )
        res = await db.execute(stmt)
        latest_doc = res.scalars().first()
        version = (latest_doc.version + 1) if latest_doc else 1
        
        db_doc = Document(
            workspace_id=workspace_id,
            filename=filename,
            storage_path=storage_path,
            status="needs_classification",
            version=version
        )
        db.add(db_doc)
        await db.flush() # Populate DB ID
        saved_docs.append(db_doc)
        
        # Create pipeline run tracker
        db_run = GraphRun(
            workspace_id=workspace_id,
            document_id=db_doc.id,
            batch_id=batch_id,
            current_node="upload",
            status="running"
        )
        db.add(db_run)
        await db.flush()
        
        # Log timeline event
        db_timeline = Timeline(
            workspace_id=workspace_id,
            event="Document uploaded",
            reason=f"File '{filename}' (v{version}) uploaded to storage.",
            actor="user:uploaded",
            section="Ingestion"
        )
        db.add(db_timeline)
        
        # Queue background processing run
        background_tasks.add_task(run_agent_pipeline, db_run.id)
        
    await db.commit()
    return saved_docs

@app.get("/documents", response_model=List[DocumentResponse])
async def get_documents(
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(desc(Document.uploaded_at))
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@app.get("/documents/{id}", response_model=DocumentResponse)
async def get_document(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_doc = await db.get(Document, id)
    if not db_doc or db_doc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found in this workspace")
    return db_doc

# ----------------- PROJECT SUMMARY BRIEF -----------------

@app.get("/project-summary", response_model=List[ProjectSummaryResponse])
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

@app.get("/project-summary/export")
async def export_project_summary(
    format: str = Query("pdf", regex="^(pdf|docx)$"),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    from backend.app.exporter import export_brief_to_pdf, export_brief_to_docx
    
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

@app.get("/project-summary/{section}", response_model=ProjectSummaryResponse)
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

@app.get("/project-summary/{section}/history", response_model=List[ProjectSummaryResponse])
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

# ----------------- CONFLICTS ENDPOINTS -----------------

@app.get("/conflicts", response_model=List[ConflictResponse])
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

@app.get("/conflicts/{id}", response_model=ConflictResponse)
async def get_conflict(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_conflict = await db.get(Conflict, id)
    if not db_conflict or db_conflict.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Conflict not found in this workspace")
    return db_conflict

# ----------------- REVIEWS QUEUE ENDPOINTS -----------------

@app.get("/review", response_model=List[ReviewResponse])
async def get_reviews(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Review)
        .where(Review.workspace_id == workspace_id)
        .order_by(desc(Review.created_at))
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Review.status == status)
    res = await db.execute(stmt)
    return res.scalars().all()

@app.post("/review/{id}/approve", response_model=ReviewResponse)
async def approve_review(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_review = await db.get(Review, id)
    if not db_review or db_review.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Review not found in this workspace")
    if db_review.status != "pending":
        raise HTTPException(status_code=400, detail="Review is already resolved")
        
    proposed = db_review.proposed_change
    section_name = proposed.get("target_section")
    new_value = proposed.get("new_value")
    source_doc = proposed.get("source_document")
    
    # Fetch current version number in this workspace
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section_name)
        .order_by(desc(ProjectSummary.version))
    )
    res = await db.execute(stmt)
    db_sec = res.scalars().first()
    latest_version = db_sec.version if db_sec else 0
    
    new_sec = ProjectSummary(
        workspace_id=workspace_id,
        section=section_name,
        content=new_value,
        version=latest_version + 1,
        last_review_id=db_review.id,
        updated_at=datetime.utcnow()
    )
    db.add(new_sec)
        
    db_review.status = "approved"
    db_review.resolved_at = datetime.utcnow()
    
    # Resolve conflicting entity link if exists
    if db_review.conflict_id:
        db_conflict = await db.get(Conflict, db_review.conflict_id)
        if db_conflict and db_conflict.workspace_id == workspace_id:
            db_conflict.resolved = True
            
    # Add timeline event
    db_timeline = Timeline(
        workspace_id=workspace_id,
        event=f"Brief Section '{section_name}' updated",
        reason=f"Approved proposed changes from {source_doc}",
        actor="user:approved",
        review_id=db_review.id,
        section=section_name
    )
    db.add(db_timeline)
    
    await db.commit()
    return db_review

@app.post("/review/{id}/reject", response_model=ReviewResponse)
async def reject_review(
    id: uuid.UUID,
    data: RejectRequest,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_review = await db.get(Review, id)
    if not db_review or db_review.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Review not found in this workspace")
    if db_review.status != "pending":
        raise HTTPException(status_code=400, detail="Review is already resolved")
        
    proposed = db_review.proposed_change
    section_name = proposed.get("target_section")
    
    db_review.status = "rejected"
    db_review.reason = data.reason
    db_review.resolved_at = datetime.utcnow()
    
    db_timeline = Timeline(
        workspace_id=workspace_id,
        event=f"Brief Section '{section_name}' update rejected",
        reason=f"Rejected draft recommendation. Reason: {data.reason}",
        actor="user:rejected",
        review_id=db_review.id,
        section=section_name
    )
    db.add(db_timeline)
    
    await db.commit()
    return db_review

# ----------------- TIMELINE AUDIT TRAIL -----------------

@app.get("/timeline", response_model=List[TimelineResponse])
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

# ----------------- PIPELINE JOBS ENDPOINTS -----------------

@app.get("/jobs", response_model=List[JobResponse])
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

@app.get("/jobs/{id}", response_model=JobResponse)
async def get_job(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_run = await db.get(GraphRun, id)
    if not db_run or db_run.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Job run not found in this workspace")
    return db_run
