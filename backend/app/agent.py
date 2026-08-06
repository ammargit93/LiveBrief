import json
import logging
from uuid import UUID
from typing import Dict, Any, List, TypedDict, Tuple
from openai import OpenAI
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.config import settings
from backend.app.database import async_session_maker
from backend.app.models import Document, Entity, Embedding, Conflict, Review, ProjectSummary, GraphRun
from backend.app.embeddings import get_embedding, cosine_similarity

# Logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Initialize Groq/OpenAI client
client = OpenAI(
    base_url=settings.GROQ_API_BASE,
    api_key=settings.GROQ_API_KEY
)

class AgentState(TypedDict):
    workspace_id: str
    document_id: str
    run_id: str
    batch_id: str
    filepath: str
    filename: str
    content: str
    chunks: List[str]
    type: str
    confidence: float
    reasoning: str
    entities: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    sections_to_draft: List[str]
    error: str

# Helper to log node transitions
async def update_job_node(db: AsyncSession, run_id: str, node_name: str, status: str = "running", error: str = None):
    stmt = (
        update(GraphRun)
        .where(GraphRun.id == run_id)
        .values(current_node=node_name, status=status, error=error)
    )
    await db.execute(stmt)
    await db.commit()

# Node 1: Classification
async def classification_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Starting classification node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "classification")

        content = state["content"]
        # Use first 3000 chars for classification to avoid token limits and stay efficient
        sample_text = content[:3000]

        prompt = f"""You are a professional software project intelligence agent. Your job is to classify the uploaded software engineering document.
Choose one type from this list:
- PRD
- Architecture
- Meeting Notes
- ADR
- Sprint Planning
- Release Notes
- API Specification
- Unknown

Document Content:
\"\"\"
{sample_text}
\"\"\"

You must respond with a raw JSON object only. Do not include any conversational text or codeblock wrappers.
JSON format:
{{
  "type": "PRD | Architecture | Meeting Notes | ADR | Sprint Planning | Release Notes | API Specification | Unknown",
  "confidence": 0.95,
  "reasoning": "Brief explanation of the classification"
}}
"""

        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            
            # Save type & confidence to DB
            stmt = (
                update(Document)
                .where(Document.id == state["document_id"])
                .values(
                    type=data.get("type", "Unknown"),
                    classification_confidence=data.get("confidence", 0.0),
                    status="processing" if data.get("confidence", 0.0) >= 0.6 else "needs_classification"
                )
            )
            await db.execute(stmt)
            await db.commit()
            
            state["type"] = data.get("type", "Unknown")
            state["confidence"] = data.get("confidence", 0.0)
            state["reasoning"] = data.get("reasoning", "")
        except Exception as e:
            logger.error(f"Error in classification: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "classification", status="failed", error=str(e))
            
    return state

# Node 2: Information Extraction
async def extraction_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting extraction node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "extraction")
        
        chunks = state["chunks"]
        # Process chunks in batches of 15 chunks (roughly 4500 tokens) to support large files
        batch_size = 15
        entities_list = []
        
        try:
            for batch_idx, start_idx in enumerate(range(0, len(chunks), batch_size)):
                batch_chunks = chunks[start_idx : start_idx + batch_size]
                batch_content = "\n\n".join(batch_chunks)
                logger.info(f"[{run_id}] Extracting facts from chunk batch {batch_idx + 1}")
                
                prompt = f"""You are an expert software project intelligence assistant. Extract structured knowledge from this portion of the document.
Document type: {state['type']}

Extract entities for the following categories if they are mentioned in this content:
- features: name, description
- technical_decisions: decision, rationale, status ("proposed" | "accepted" | "superseded")
- components: name, description
- risks: description, severity ("low" | "medium" | "high"), mitigation (or null)
- action_items: description, owner (or null), due_date (ISO-date or null)
- deadlines: label, date (ISO-date)
- owners: name, role (or null), area (or null)

For each extracted item, you MUST include a short 'source_excerpt' (maximum one sentence) from the content that directly supports the extraction.

Content portion:
\"\"\"
{batch_content}
\"\"\"

You must respond with a raw JSON object only.
JSON format:
{{
  "features": [{{ "name": "...", "description": "...", "source_excerpt": "..." }}],
  "technical_decisions": [{{ "decision": "...", "rationale": "...", "status": "proposed|accepted|superseded", "source_excerpt": "..." }}],
  "components": [{{ "name": "...", "description": "...", "source_excerpt": "..." }}],
  "risks": [{{ "description": "...", "severity": "low|medium|high", "mitigation": "...", "source_excerpt": "..." }}],
  "action_items": [{{ "description": "...", "owner": "...", "due_date": "...", "source_excerpt": "..." }}],
  "deadlines": [{{ "label": "...", "date": "...", "source_excerpt": "..." }}],
  "owners": [{{ "name": "...", "role": "...", "area": "...", "source_excerpt": "..." }}]
}}
"""

                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                extracted_data = json.loads(response.choices[0].message.content)
                
                # Map entity types and save to DB
                for key, items in extracted_data.items():
                    type_map = {
                        "features": "feature",
                        "technical_decisions": "decision",
                        "components": "component",
                        "risks": "risk",
                        "action_items": "action_item",
                        "deadlines": "deadline",
                        "owners": "owner"
                    }
                    entity_type = type_map.get(key, key)
                    if not isinstance(items, list):
                        continue
                        
                    for item in items:
                        if not item:
                            continue
                        source_excerpt = item.pop("source_excerpt", "")
                        
                        db_entity = Entity(
                            document_id=doc_id,
                            type=entity_type,
                            value=item,
                            source_excerpt=source_excerpt
                        )
                        db.add(db_entity)
                        await db.flush() # populate ID
                        
                        entities_list.append({
                            "id": str(db_entity.id),
                            "document_id": str(doc_id),
                            "type": entity_type,
                            "value": item,
                            "source_excerpt": source_excerpt
                        })
                        
            # Also save embeddings for chunked text
            for i, chunk in enumerate(state["chunks"]):
                chunk_vector = get_embedding(chunk)
                db_emb = Embedding(
                    document_id=doc_id,
                    chunk=chunk,
                    chunk_index=i,
                    embedding=chunk_vector
                )
                db.add(db_emb)
                
            await db.commit()
            state["entities"] = entities_list
        except Exception as e:
            logger.error(f"Error in extraction: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "extraction", status="failed", error=str(e))
            
    return state

# Node 3: Knowledge Merge (Comparing new entities with existing ones using Python cosine similarity)
async def knowledge_merge_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting knowledge merge node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "knowledge_merge")
        
        new_entities = state["entities"]
        conflicts_to_check = []
        
        try:
            # Query existing entities of similar categories NOT from the current document, isolated by workspace
            stmt = select(Entity).join(Document).where(Entity.document_id != doc_id).where(Document.workspace_id == state["workspace_id"])
            res = await db.execute(stmt)
            existing_entities = res.scalars().all()
            
            for new_ent in new_entities:
                new_type = new_ent["type"]
                new_val_str = json.dumps(new_ent["value"])
                new_vec = get_embedding(new_val_str)
                
                for ext_ent in existing_entities:
                    if ext_ent.type == new_type:
                        ext_val_str = json.dumps(ext_ent.value)
                        ext_vec = get_embedding(ext_val_str)
                        
                        similarity = cosine_similarity(new_vec, ext_vec)
                        # Threshold for merging / conflict check candidate: 0.4
                        if similarity >= 0.40:
                            conflicts_to_check.append({
                                "new_entity": new_ent,
                                "existing_entity": {
                                    "id": str(ext_ent.id),
                                    "type": ext_ent.type,
                                    "value": ext_ent.value,
                                    "source_excerpt": ext_ent.source_excerpt,
                                    "document_id": str(ext_ent.document_id)
                                }
                            })
                            
            state["conflicts"] = conflicts_to_check
        except Exception as e:
            logger.error(f"Error in knowledge merge: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "knowledge_merge", status="failed", error=str(e))
            
    return state

# Node 4: Conflict Detection
async def conflict_detection_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Starting conflict detection node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "conflict_detection")
        
        candidates = state["conflicts"]
        detected_conflicts = []
        affected_sections = set()
        
        # Mapping categories to sections
        category_to_sections = {
            "feature": ["Major Features"],
            "decision": ["Current Decisions", "Pending Decisions"],
            "component": ["Architecture"],
            "risk": ["Known Risks"],
            "action_item": ["Timeline"],
            "deadline": ["Timeline"],
            "owner": ["Project Overview"]
        }
        
        try:
            for cand in candidates:
                new_ent = cand["new_entity"]
                existing_ent = cand["existing_entity"]
                
                # Fetch filenames of source docs for better context
                new_doc = await db.get(Document, new_ent["document_id"])
                existing_doc = await db.get(Document, existing_ent["document_id"])
                
                new_source_name = new_doc.filename if new_doc else "New Document"
                existing_source_name = existing_doc.filename if existing_doc else "Existing Document"

                prompt = f"""You are a senior software product analyst. Compare the following two entities extracted from different project documents.
Entity Type: {new_ent['type']}

Existing Item (from {existing_source_name}):
Value: {json.dumps(existing_ent['value'])}
Excerpt: "{existing_ent['source_excerpt']}"

New Item (from {new_source_name}):
Value: {json.dumps(new_ent['value'])}
Excerpt: "{new_ent['source_excerpt']}"

Evaluate:
1. Direct Contradiction: Do these statements conflict? (e.g. Auth is Auth0 vs Auth is custom JWT).
2. Staleness / Superseding: Does the new item update, override, or replace the old one? (e.g. sprint deadline changed from Aug 10 to Aug 15).
3. If they are identical or complement each other without conflict, they do NOT conflict.

You must respond with a raw JSON object only.
JSON format:
{{
  "conflict": true / false,
  "category": "Name of the feature/decision/topic",
  "severity": "high | medium | low",
  "explanation": "Detailed explanation of the contradiction or why it is superseded"
}}
"""

                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                res_data = json.loads(response.choices[0].message.content)
                
                if res_data.get("conflict", False):
                    # Save conflict to database
                    db_conflict = Conflict(
                        workspace_id=state["workspace_id"],
                        category=res_data.get("category", new_ent["type"]),
                        description=res_data.get("explanation", ""),
                        severity=res_data.get("severity", "medium"),
                        existing_entity_id=existing_ent["id"],
                        new_entity_id=new_ent["id"],
                        resolved=False
                    )
                    db.add(db_conflict)
                    await db.flush()
                    
                    detected_conflicts.append({
                        "id": str(db_conflict.id),
                        "category": db_conflict.category,
                        "description": db_conflict.description,
                        "severity": db_conflict.severity
                    })
                    
                    # Mark section as needing drafting
                    sections = category_to_sections.get(new_ent["type"], ["Project Overview"])
                    for s in sections:
                        affected_sections.add(s)
            
            # If no conflicts, any new entity should still trigger section updates
            if not affected_sections:
                for ent in state["entities"]:
                    sections = category_to_sections.get(ent["type"], ["Project Overview"])
                    for s in sections:
                        affected_sections.add(s)
                        
            await db.commit()
            state["sections_to_draft"] = list(affected_sections)
        except Exception as e:
            logger.error(f"Error in conflict detection: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "conflict_detection", status="failed", error=str(e))
            
    return state

# Node 5: Generate Project Brief Updates
async def generate_brief_updates_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting generate brief updates node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "generate_brief_updates")
        
        sections = state["sections_to_draft"]
        
        try:
            # Load the current document
            doc = await db.get(Document, doc_id)
            doc_name = doc.filename if doc else "Document"
            
            for section_name in sections:
                # 1. Fetch current content of the section if it exists, isolated by workspace and ordering by version descending
                stmt = select(ProjectSummary).where(ProjectSummary.workspace_id == state["workspace_id"]).where(ProjectSummary.section == section_name).order_by(desc(ProjectSummary.version))
                res = await db.execute(stmt)
                summary_section = res.scalars().first()
                existing_content = summary_section.content if summary_section else "(This section is currently empty.)"
                
                # 2. Collect all entities that belong to this section category
                # Mapping section to entity type
                section_to_entity_types = {
                    "Project Overview": ["owner", "action_item"],
                    "Architecture": ["component"],
                    "Major Features": ["feature"],
                    "Current Decisions": ["decision"],
                    "Known Risks": ["risk"],
                    "Pending Decisions": ["decision"],
                    "Open Questions": ["decision", "risk"],
                    "Timeline": ["deadline", "action_item"]
                }
                
                ent_types = section_to_entity_types.get(section_name, [])
                
                # Fetch both existing active entities and the new ones for this category, isolated by workspace
                ent_stmt = select(Entity).join(Document).where(Entity.type.in_(ent_types)).where(Document.workspace_id == state["workspace_id"])
                ent_res = await db.execute(ent_stmt)
                all_entities = ent_res.scalars().all()
                
                entities_str = "\n".join([
                    f"- {ent.type.upper()}: {json.dumps(ent.value)} (from doc_id: {ent.document_id})"
                    for ent in all_entities
                ])
                
                # Ask LLM to draft the updated section content
                prompt = f"""You are a professional technical writer and system architect. Update the Section '{section_name}' of our software project brief.
Here is the current content of Section '{section_name}':
\"\"\"
{existing_content}
\"\"\"

Here are the extracted structured facts and decisions we must incorporate (both existing and new updates):
\"\"\"
{entities_str}
\"\"\"

Please draft a clean, professional, and well-structured Markdown version of Section '{section_name}'.
- Do not add any introductory or concluding comments.
- Start directly with the updated Markdown content.
- Do not repeat information redundantly.
- Keep the style premium, high-level, and clean.
"""
                
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                draft_content = response.choices[0].message.content.strip()
                
                # Find if there is a linked conflict for this run
                # We can query conflicts related to the new entities
                conflict_id = None
                new_ent_ids = [UUID(ent["id"]) for ent in state["entities"]]
                if new_ent_ids:
                    conf_stmt = select(Conflict).where(Conflict.workspace_id == state["workspace_id"]).where(Conflict.new_entity_id.in_(new_ent_ids)).limit(1)
                    conf_res = await db.execute(conf_stmt)
                    conf_item = conf_res.scalars().first()
                    if conf_item:
                        conflict_id = conf_item.id
                
                # Create a pending Review row
                proposed_change = {
                    "target_section": section_name,
                    "old_value": existing_content,
                    "new_value": draft_content,
                    "source_document": doc_name
                }
                
                db_review = Review(
                    workspace_id=state["workspace_id"],
                    proposed_change=proposed_change,
                    conflict_id=conflict_id,
                    status="pending"
                )
                db.add(db_review)
                
            # Set job status to waiting_for_review
            await update_job_node(db, run_id, "generate_brief_updates", status="waiting_for_review")
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error generating brief updates: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "generate_brief_updates", status="failed", error=str(e))
            
    return state

# Full pipeline execution helper (LangGraph-like state transition)
async def run_agent_pipeline(run_id: str):
    logger.info(f"Starting agent pipeline execution for run_id: {run_id}")
    
    async with async_session_maker() as db:
        # Load run
        run_stmt = select(GraphRun).where(GraphRun.id == run_id)
        run_res = await db.execute(run_stmt)
        run = run_res.scalars().first()
        if not run:
            logger.error(f"GraphRun {run_id} not found.")
            return
            
        # Load document
        doc = await db.get(Document, run.document_id)
        if not doc:
            logger.error(f"Document {run.document_id} not found.")
            return
            
    # Read storage file
    try:
        from backend.app.parsers import extract_text_and_type, chunk_text
        content, file_type = extract_text_and_type(doc.storage_path, doc.filename)
        chunks = chunk_text(content)
    except Exception as e:
        logger.error(f"Failed parsing file: {e}")
        async with async_session_maker() as db:
            doc.status = "failed"
            await db.merge(doc)
            await update_job_node(db, run_id, "upload", status="failed", error=f"Parsing error: {e}")
        return
        
    state: AgentState = {
        "workspace_id": str(run.workspace_id),
        "document_id": str(doc.id),
        "run_id": str(run_id),
        "batch_id": str(run.batch_id),
        "filepath": doc.storage_path,
        "filename": doc.filename,
        "content": content,
        "chunks": chunks,
        "type": "Unknown",
        "confidence": 0.0,
        "reasoning": "",
        "entities": [],
        "conflicts": [],
        "sections_to_draft": [],
        "error": ""
    }
    
    # Execute node state transitions
    state = await classification_node(state)
    if state.get("error"):
        return
        
    state = await extraction_node(state)
    if state.get("error"):
        return
        
    state = await knowledge_merge_node(state)
    if state.get("error"):
        return
        
    state = await conflict_detection_node(state)
    if state.get("error"):
        return
        
    state = await generate_brief_updates_node(state)
    if state.get("error"):
        return
        
    logger.info(f"[{run_id}] Finished processing up to interrupt stage successfully.")
