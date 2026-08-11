import os
import sys
import json
import logging
from uuid import UUID
from datetime import datetime
from typing import List, Optional, Dict, Any

# Temporarily redirect stdout to stderr during imports to prevent stdout pollution
old_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    from mcp.server import MCPServer
    from sqlalchemy import select, update, desc
    from sqlalchemy.orm import joinedload
    from backend.app.core.config import settings
    from backend.app.core.database import async_session_maker
    from backend.app.models import Workspace, Document, Entity, Conflict, Review, ProjectSummary, Timeline, GraphRun
    from backend.app.services.agent_service import run_agent_pipeline
    from backend.app.routers.deps import create_workspace_with_sections
finally:
    sys.stdout = old_stdout

# Configure logging to stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("mcp-server")

# Initialize MCP Server
mcp = MCPServer("LiveBrief")

@mcp.tool()
async def create_workspace(name: str) -> Dict[str, Any]:
    """Create a new workspace in LiveBrief with default template sections.
    
    Args:
        name: Unique name for the new workspace.
        
    Returns:
        The created workspace details (workspace_id and name).
    """
    if not name or not name.strip():
        raise ValueError("Workspace name cannot be empty")
        
    async with async_session_maker() as db:
        stmt = select(Workspace).where(Workspace.name == name.strip())
        res = await db.execute(stmt)
        if res.scalars().first():
            raise ValueError(f"Workspace name '{name}' already exists")
            
        ws = await create_workspace_with_sections(name.strip(), db)
        await db.commit()
        return {"workspace_id": str(ws.id), "name": ws.name}

@mcp.tool()
async def list_workspaces() -> List[Dict[str, Any]]:
    """List all available workspaces in the LiveBrief database.
    
    Returns:
        List of workspaces (each containing workspace_id and name).
    """
    async with async_session_maker() as db:
        stmt = select(Workspace).order_by(Workspace.name)
        res = await db.execute(stmt)
        workspaces = res.scalars().all()
        return [{"workspace_id": str(w.id), "name": w.name} for w in workspaces]

@mcp.tool()
async def ingest_document(workspace_id: str, filename: str, content: str) -> Dict[str, Any]:
    """Upload and ingest a document into a workspace, initiating the agent processing run.
    
    Args:
        workspace_id: UUID of the workspace to ingest the document into.
        filename: Name of the file (must end with .md, .pdf, or .docx).
        content: Raw text content of the document.
        
    Returns:
        Ingestion details containing document_id and run_id.
    """
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise ValueError("Invalid workspace UUID format")
        
    if not filename.lower().endswith(('.md', '.pdf', '.docx')):
        raise ValueError("Invalid file type. Only .md, .pdf, and .docx are supported")
        
    if not content or not content.strip():
        raise ValueError("Document content cannot be empty")
        
    async with async_session_maker() as db:
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise ValueError(f"Workspace with ID {workspace_id} does not exist")
            
        upload_dir = settings.STORAGE_PATH
        os.makedirs(upload_dir, exist_ok=True)
        
        import uuid
        storage_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{filename}")
        
        try:
            with open(storage_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            raise ValueError(f"Failed to write file to storage: {str(e)}")
            
        # Versioning: check if filename exists in this workspace
        stmt = (
            select(Document)
            .where(Document.workspace_id == ws_uuid)
            .where(Document.filename == filename)
            .order_by(desc(Document.version))
        )
        res = await db.execute(stmt)
        latest_doc = res.scalars().first()
        version = (latest_doc.version + 1) if latest_doc else 1
        
        doc = Document(
            workspace_id=ws_uuid,
            filename=filename,
            storage_path=storage_path,
            status="needs_classification",
            version=version
        )
        db.add(doc)
        await db.flush()
        
        # Create pipeline run tracker
        db_run = GraphRun(
            workspace_id=ws_uuid,
            document_id=doc.id,
            batch_id=uuid.uuid4(),
            current_node="upload",
            status="running"
        )
        db.add(db_run)
        await db.flush()
        
        # Log timeline event
        db_timeline = Timeline(
            workspace_id=ws_uuid,
            event="Document uploaded via MCP",
            reason=f"File '{filename}' (v{version}) ingested via MCP tool.",
            actor="mcp:uploaded",
            section="Ingestion"
        )
        db.add(db_timeline)
        await db.commit()
        
        # Trigger the pipeline background task
        import asyncio
        asyncio.create_task(run_agent_pipeline(str(db_run.id)))
        
        return {"document_id": str(doc.id), "run_id": str(db_run.id)}

@mcp.tool()
async def get_run_status(run_id: str) -> Dict[str, Any]:
    """Retrieve execution status, current node, planner decisions, and errors for a job run.
    
    Args:
        run_id: UUID of the target GraphRun.
        
    Returns:
        Run status details.
    """
    try:
        run_uuid = UUID(run_id)
    except ValueError:
        raise ValueError("Invalid run UUID format")
        
    async with async_session_maker() as db:
        run = await db.get(GraphRun, run_uuid)
        if not run:
            raise ValueError(f"GraphRun with ID {run_id} does not exist")
            
        planner_data = None
        if run.planner_decision:
            planner_data = {
                "affected_sections": run.planner_decision.get("affected_sections", []),
                "entity_types_to_extract": run.planner_decision.get("entity_types_to_extract", []),
                "conflict_check": run.planner_decision.get("requires_conflict_check", True),
                "timeline_update": run.planner_decision.get("requires_timeline_update", True),
                "reasoning": run.planner_decision.get("reasoning", "")
            }
            
        return {
            "run_id": str(run.id),
            "status": run.status,
            "current_node": run.current_node,
            "planner": planner_data,
            "error": run.error,
            "started_at": run.started_at.isoformat(),
            "updated_at": run.updated_at.isoformat()
        }

@mcp.tool()
async def get_project_brief(workspace_id: str) -> List[Dict[str, Any]]:
    """Retrieve the current living Project Brief sections and their versions for a workspace.
    
    Args:
        workspace_id: UUID of the target workspace.
        
    Returns:
        List of project brief sections.
    """
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise ValueError("Invalid workspace UUID format")
        
    async with async_session_maker() as db:
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise ValueError(f"Workspace with ID {workspace_id} does not exist")
            
        stmt = (
            select(ProjectSummary)
            .where(ProjectSummary.workspace_id == ws_uuid)
            .distinct(ProjectSummary.section)
            .order_by(ProjectSummary.section, desc(ProjectSummary.version))
        )
        res = await db.execute(stmt)
        sections = res.scalars().all()
        
        return [
            {
                "section": s.section,
                "version": s.version,
                "content": s.content,
                "updated_at": s.updated_at.isoformat(),
                "last_review_id": str(s.last_review_id) if s.last_review_id else None
            }
            for s in sections
        ]

@mcp.tool()
async def get_conflicts(workspace_id: str) -> List[Dict[str, Any]]:
    """Retrieve unresolved conflicts between documents in a workspace, including recommendations.
    
    Args:
        workspace_id: UUID of the workspace.
        
    Returns:
        List of active conflicts.
    """
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise ValueError("Invalid workspace UUID format")
        
    async with async_session_maker() as db:
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise ValueError(f"Workspace with ID {workspace_id} does not exist")
            
        stmt = (
            select(Conflict)
            .options(
                joinedload(Conflict.existing_entity).joinedload(Entity.document),
                joinedload(Conflict.new_entity).joinedload(Entity.document)
            )
            .where(Conflict.workspace_id == ws_uuid)
            .where(Conflict.resolved == False)
            .order_by(desc(Conflict.created_at))
        )
        res = await db.execute(stmt)
        conflicts = res.scalars().all()
        
        results = []
        for c in conflicts:
            rec_stmt = select(Review).where(Review.conflict_id == c.id).where(Review.status == "pending")
            rec_res = await db.execute(rec_stmt)
            review = rec_res.scalars().first()
            recommendation = review.proposed_change.get("new_value") if review else None
            
            existing_doc = c.existing_entity.document.filename if c.existing_entity and c.existing_entity.document else None
            new_doc = c.new_entity.document.filename if c.new_entity and c.new_entity.document else None
            
            results.append({
                "conflict_id": str(c.id),
                "category": c.category,
                "description": c.description,
                "severity": c.severity,
                "created_at": c.created_at.isoformat(),
                "source_entities": {
                    "existing": {
                        "value": c.existing_entity.value if c.existing_entity else None,
                        "source_excerpt": c.existing_entity.source_excerpt if c.existing_entity else None,
                        "document": existing_doc
                    },
                    "new": {
                        "value": c.new_entity.value if c.new_entity else None,
                        "source_excerpt": c.new_entity.source_excerpt if c.new_entity else None,
                        "document": new_doc
                    }
                },
                "recommendation": recommendation
            })
            
        return results

@mcp.tool()
async def get_pending_reviews(workspace_id: str) -> List[Dict[str, Any]]:
    """Retrieve pending proposed brief updates in the workspace's review queue.
    
    Args:
        workspace_id: UUID of the target workspace.
        
    Returns:
        List of pending reviews.
    """
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise ValueError("Invalid workspace UUID format")
        
    async with async_session_maker() as db:
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise ValueError(f"Workspace with ID {workspace_id} does not exist")
            
        stmt = select(Review).where(Review.workspace_id == ws_uuid).where(Review.status == "pending").order_by(desc(Review.created_at))
        res = await db.execute(stmt)
        reviews = res.scalars().all()
        
        return [
            {
                "review_id": str(r.id),
                "proposed_change": {
                    "target_section": r.proposed_change.get("target_section"),
                    "old_value": r.proposed_change.get("old_value"),
                    "new_value": r.proposed_change.get("new_value"),
                    "source_document": r.proposed_change.get("source_document")
                },
                "conflict_id": str(r.conflict_id) if r.conflict_id else None,
                "status": r.status,
                "created_at": r.created_at.isoformat()
            }
            for r in reviews
        ]

@mcp.tool()
async def approve_review(review_id: str) -> Dict[str, Any]:
    """Approve a pending review, committing the recommended changes to the Project Brief.
    
    Args:
        review_id: UUID of the target Review.
        
    Returns:
        Summary of the resolved review state and the resulting brief version.
    """
    try:
        review_uuid = UUID(review_id)
    except ValueError:
        raise ValueError("Invalid review UUID format")
        
    async with async_session_maker() as db:
        db_review = await db.get(Review, review_uuid)
        if not db_review:
            raise ValueError(f"Review with ID {review_id} does not exist")
            
        if db_review.status != "pending":
            raise ValueError(f"Review with ID {review_id} is already resolved with status: {db_review.status}")
            
        workspace_id = db_review.workspace_id
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
            event=f"Brief Section '{section_name}' updated via MCP",
            reason=f"Approved proposed changes from {source_doc}",
            actor="mcp:approved",
            review_id=db_review.id,
            section=section_name
        )
        db.add(db_timeline)
        await db.commit()
        
        return {
            "review_id": str(db_review.id),
            "status": db_review.status,
            "resolved_at": db_review.resolved_at.isoformat(),
            "brief_section": section_name,
            "new_version": latest_version + 1
        }

@mcp.tool()
async def reject_review(review_id: str, rejection_reason: str) -> Dict[str, Any]:
    """Reject a pending review, discarding the recommended changes.
    
    Args:
        review_id: UUID of the target Review.
        rejection_reason: Explanation note for the rejection.
        
    Returns:
        Summary of the resolved review state.
    """
    try:
        review_uuid = UUID(review_id)
    except ValueError:
        raise ValueError("Invalid review UUID format")
        
    if not rejection_reason or not rejection_reason.strip():
        raise ValueError("Rejection reason cannot be empty")
        
    async with async_session_maker() as db:
        db_review = await db.get(Review, review_uuid)
        if not db_review:
            raise ValueError(f"Review with ID {review_id} does not exist")
            
        if db_review.status != "pending":
            raise ValueError(f"Review with ID {review_id} is already resolved with status: {db_review.status}")
            
        workspace_id = db_review.workspace_id
        proposed = db_review.proposed_change
        section_name = proposed.get("target_section")
        
        db_review.status = "rejected"
        db_review.reason = rejection_reason.strip()
        db_review.resolved_at = datetime.utcnow()
        
        db_timeline = Timeline(
            workspace_id=workspace_id,
            event=f"Brief Section '{section_name}' update rejected via MCP",
            reason=f"Rejected draft recommendation. Reason: {rejection_reason.strip()}",
            actor="mcp:rejected",
            review_id=db_review.id,
            section=section_name
        )
        db.add(db_timeline)
        await db.commit()
        
        return {
            "review_id": str(db_review.id),
            "status": db_review.status,
            "resolved_at": db_review.resolved_at.isoformat(),
            "reason": db_review.reason
        }

@mcp.tool()
async def get_audit_trail(workspace_id: str) -> List[Dict[str, Any]]:
    """Retrieve chronological timeline/audit events for a workspace.
    
    Args:
        workspace_id: UUID of the target workspace.
        
    Returns:
        List of audit events.
    """
    try:
        ws_uuid = UUID(workspace_id)
    except ValueError:
        raise ValueError("Invalid workspace UUID format")
        
    async with async_session_maker() as db:
        ws = await db.get(Workspace, ws_uuid)
        if not ws:
            raise ValueError(f"Workspace with ID {workspace_id} does not exist")
            
        stmt = select(Timeline).where(Timeline.workspace_id == ws_uuid).order_by(desc(Timeline.timestamp))
        res = await db.execute(stmt)
        events = res.scalars().all()
        
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "event": e.event,
                "reason": e.reason,
                "actor": e.actor,
                "section": e.section
            }
            for e in events
        ]

@mcp.tool()
async def resume_run(run_id: str) -> Dict[str, Any]:
    """Resume a failed GraphRun pipeline processing job.
    
    Args:
        run_id: UUID of the failed GraphRun.
        
    Returns:
        The updated GraphRun status.
    """
    try:
        run_uuid = UUID(run_id)
    except ValueError:
        raise ValueError("Invalid run UUID format")
        
    async with async_session_maker() as db:
        run = await db.get(GraphRun, run_uuid)
        if not run:
            raise ValueError(f"GraphRun with ID {run_id} does not exist")
            
        if run.status not in ["failed", "interrupted/recoverable"]:
            raise ValueError(f"Run is in status '{run.status}' and cannot be resumed (only failed or interrupted runs can be resumed)")
            
        run.status = "running"
        run.error = None
        await db.commit()
        
        # Trigger the pipeline background task
        import asyncio
        asyncio.create_task(run_agent_pipeline(str(run.id)))
        
        return {
            "run_id": str(run.id),
            "status": run.status,
            "current_node": run.current_node
        }

if __name__ == "__main__":
    mcp.run()
