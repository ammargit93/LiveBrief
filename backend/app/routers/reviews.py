import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models import Review, ProjectSummary, Conflict, Timeline
from backend.app.schemas import ReviewResponse, RejectRequest, UpdateReviewRequest
from backend.app.routers.deps import get_active_workspace_id

router = APIRouter(prefix="/review", tags=["reviews"])

@router.get("", response_model=List[ReviewResponse])
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

@router.post("/{id}/approve", response_model=ReviewResponse)
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
    
    # Fetch current section in this workspace
    stmt = (
        select(ProjectSummary)
        .where(ProjectSummary.workspace_id == workspace_id)
        .where(ProjectSummary.section == section_name)
    )
    res = await db.execute(stmt)
    db_sec = res.scalars().first()
    
    if db_sec:
        db_sec.content = new_value
        db_sec.last_review_id = db_review.id
        db_sec.updated_at = datetime.utcnow()
    else:
        new_sec = ProjectSummary(
            workspace_id=workspace_id,
            section=section_name,
            content=new_value,
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

@router.post("/{id}/reject", response_model=ReviewResponse)
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

@router.put("/{id}", response_model=ReviewResponse)
async def update_review(
    id: uuid.UUID,
    data: UpdateReviewRequest,
    workspace_id: uuid.UUID = Depends(get_active_workspace_id),
    db: AsyncSession = Depends(get_db)
):
    db_review = await db.get(Review, id)
    if not db_review or db_review.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Review not found in this workspace")
    if db_review.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending reviews can be updated")
        
    proposed = dict(db_review.proposed_change) if db_review.proposed_change else {}
    if data.target_section is not None:
        proposed["target_section"] = data.target_section
        proposed["section"] = data.target_section
    if data.new_value is not None:
        proposed["new_value"] = data.new_value
        
    db_review.proposed_change = proposed
    
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(db_review, "proposed_change")
    
    await db.commit()
    await db.refresh(db_review)
    return db_review

