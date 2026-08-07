import os
import uuid
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models import Document, GraphRun, Timeline
from backend.app.schemas import DocumentResponse
from backend.app.routers.deps import get_active_workspace_id
from backend.app.services.agent_service import run_agent_pipeline

logger = logging.getLogger("main")
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=List[DocumentResponse])
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

@router.get("", response_model=List[DocumentResponse])
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

@router.get("/{id}", response_model=DocumentResponse)
async def get_document(
    id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_doc = await db.get(Document, id)
    if not db_doc or db_doc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found in this workspace")
    return db_doc
