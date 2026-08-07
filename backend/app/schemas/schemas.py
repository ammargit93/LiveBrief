from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any

class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    storage_path: str
    type: Optional[str]
    classification_confidence: Optional[float]
    status: str
    uploaded_at: datetime
    version: int

    class Config:
        from_attributes = True

class ConflictResponse(BaseModel):
    id: UUID
    category: str
    description: str
    severity: str
    existing_entity_id: Optional[UUID]
    new_entity_id: Optional[UUID]
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ProjectSummaryResponse(BaseModel):
    id: UUID
    section: str
    content: str
    version: int
    updated_at: datetime
    last_review_id: Optional[UUID]

    class Config:
        from_attributes = True

class ReviewResponse(BaseModel):
    id: UUID
    proposed_change: Dict[str, Any] # {old_value, new_value, target_section, source_document}
    conflict_id: Optional[UUID]
    status: str
    reason: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True

class RejectRequest(BaseModel):
    reason: Optional[str] = None

class TimelineResponse(BaseModel):
    id: UUID
    event: str
    reason: str
    actor: str
    review_id: Optional[UUID]
    section: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True

class PlannerDecision(BaseModel):
    affected_sections: List[str]
    entity_types_to_extract: List[str]
    requires_conflict_check: bool
    requires_timeline_update: bool
    reasoning: str

class JobResponse(BaseModel):
    id: UUID
    document_id: UUID
    batch_id: UUID
    current_node: str
    status: str
    error: Optional[str]
    planner_decision: Optional[Dict[str, Any]] = None
    started_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
