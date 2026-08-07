import sys
import json
import logging
import asyncio
from uuid import UUID
from typing import Dict, Any, List, TypedDict, Tuple

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from backend.app.core.config import settings
from backend.app.core.database import async_session_maker
from backend.app.models import Document, Entity, Embedding, Conflict, Review, ProjectSummary, GraphRun
from backend.app.services.embedding_service import get_embedding, cosine_similarity

# Logger configuration
root_logger = logging.getLogger()
if not root_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)

# Helper to call LLM using LangChain ChatGroq
def call_llm(prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
    from langchain_groq import ChatGroq
    if json_mode:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature
        ).bind(response_format={"type": "json_object"})
    else:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature
        )
    response = llm.invoke(prompt)
    return response.content

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
    planner_decision: Dict[str, Any]

# Helper to log node transitions
async def update_job_node(db: AsyncSession, run_id: str, node_name: str, status: str = "running", error: str = None, planner_decision: dict = None):
    values = {"current_node": node_name, "status": status, "error": error}
    if planner_decision is not None:
        values["planner_decision"] = planner_decision
    stmt = (
        update(GraphRun)
        .where(GraphRun.id == run_id)
        .values(**values)
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
            content = call_llm(prompt, temperature=0.0, json_mode=True)
            data = json.loads(content)
            
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

# Node 1.5: Planner Node
async def planner_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Starting planner node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "planner")
        
        # 1. Fetch existing project brief section metadata for context
        stmt = select(ProjectSummary).where(ProjectSummary.workspace_id == state["workspace_id"]).order_by(ProjectSummary.section)
        res = await db.execute(stmt)
        summaries = res.scalars().all()
        
        summary_meta = []
        for s in summaries:
            summary_meta.append(f"- Section '{s.section}': {len(s.content)} characters of content")
        summary_meta_str = "\n".join(summary_meta) if summary_meta else "No sections drafted yet (this is the first document)."
        
        workspace_info = f"Existing Brief Sections in Workspace:\n{summary_meta_str}"
        
        # 2. Build the planner prompt
        prompt = f"""You are the Project Brief Planner. Your job is to plan the processing pipeline for an ingested document.
Determine which brief sections are affected and which entity categories need to be extracted from this document to update the brief correctly.

Workspace Context:
{workspace_info}

Document Details:
- Name: {state["filename"]}
- Classification Type: {state["type"]}

Document Excerpt (First 6000 characters):
\"\"\"
{state["content"][:6000]}
\"\"\"

Output format:
You must respond with a raw JSON object matching this schema.
JSON structure:
{{
  "affected_sections": ["Overview", "Architecture", "Major Features", "Current Decisions", "Known Risks", "Pending Decisions", "Open Questions", "Timeline"],
  "entity_types_to_extract": ["feature", "decision", "component", "risk", "action_item", "deadline", "owner"],
  "requires_conflict_check": true | false,
  "requires_timeline_update": true | false,
  "reasoning": "Brief explanation of the decisions"
}}
"""
        try:
            content = call_llm(prompt, temperature=0.0, json_mode=True)
            from backend.app.schemas.schemas import PlannerDecision
            decision = PlannerDecision.model_validate_json(content)
            
            # Save the decision to state and persist in DB
            state["planner_decision"] = decision.model_dump()
            await update_job_node(db, run_id, "planner", planner_decision=decision.model_dump())
            
        except Exception as e:
            logger.error(f"[{run_id}] Planner failed, falling back to full pipeline: {e}")
            from backend.app.schemas.schemas import PlannerDecision
            fallback_decision = PlannerDecision(
                affected_sections=[
                    "Project Overview",
                    "Architecture",
                    "Major Features",
                    "Current Decisions",
                    "Known Risks",
                    "Pending Decisions",
                    "Open Questions",
                    "Timeline"
                ],
                entity_types_to_extract=["feature", "decision", "component", "risk", "action_item", "deadline", "owner"],
                requires_conflict_check=True,
                requires_timeline_update=True,
                reasoning=f"Planner fallback triggered due to error: {str(e)}"
            )
            state["planner_decision"] = fallback_decision.model_dump()
            await update_job_node(db, run_id, "planner", planner_decision=fallback_decision.model_dump())
            
    return state

# Node 2: Information Extraction
async def extraction_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting extraction node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "extraction")
        
        allowed_types = state["planner_decision"].get("entity_types_to_extract", [])
        if not allowed_types:
            logger.info(f"[{run_id}] Skipping extraction node as requested by the plan.")
            await update_job_node(db, run_id, "extraction", status="complete")
            return state

        chunks = state["chunks"]
        # Process chunks in smaller batches to avoid token per minute (TPM) limit on free tier
        batch_size = 3
        entities_list = []
        
        category_prompts = {
            "feature": "- features: name, description, page (integer, based on nearby [Page X] marker if present, default to 1)",
            "decision": '- technical_decisions: decision, rationale, status ("proposed" | "accepted" | "superseded"), page (integer, based on nearby [Page X] marker if present, default to 1)',
            "component": "- components: name, description, page (integer, based on nearby [Page X] marker if present, default to 1)",
            "risk": '- risks: description, severity ("low" | "medium" | "high"), mitigation (or null), page (integer, based on nearby [Page X] marker if present, default to 1)',
            "action_item": "- action_items: description, owner (or null), due_date (ISO-date or null), page (integer, based on nearby [Page X] marker if present, default to 1)",
            "deadline": "- deadlines: label, date (ISO-date), page (integer, based on nearby [Page X] marker if present, default to 1)",
            "owner": "- owners: name, role (or null), area (or null), page (integer, based on nearby [Page X] marker if present, default to 1)"
        }
        active_prompts = []
        for t in allowed_types:
            if t in category_prompts:
                active_prompts.append(category_prompts[t])
        categories_to_extract_str = "\n".join(active_prompts)

        try:
            for batch_idx, start_idx in enumerate(range(0, len(chunks), batch_size)):
                batch_chunks = chunks[start_idx : start_idx + batch_size]
                batch_content = "\n\n".join(batch_chunks)
                logger.info(f"[{run_id}] Extracting facts from chunk batch {batch_idx + 1}")
                
                prompt = f"""You are an expert software project intelligence assistant. Extract structured knowledge from this portion of the document.
Document type: {state['type']}

Extract entities for the following categories if they are mentioned in this content:
{categories_to_extract_str}

For each extracted item:
1. You MUST include a short 'source_excerpt' (maximum one sentence) from the content that directly supports the extraction.
2. Identify the page number where the information is located based on nearby page markers like `[Page X]` in the content portion. Set the 'page' field (integer) to that number. If there are no page markers, default the page to 1.

Content portion:
\"\"\"
{batch_content}
\"\"\"

You must respond with a raw JSON object only.
JSON format:
{{
  "features": [{{ "name": "...", "description": "...", "source_excerpt": "...", "page": 1 }}],
  "technical_decisions": [{{ "decision": "...", "rationale": "...", "status": "proposed|accepted|superseded", "source_excerpt": "...", "page": 1 }}],
  "components": [{{ "name": "...", "description": "...", "source_excerpt": "...", "page": 1 }}],
  "risks": [{{ "description": "...", "severity": "low|medium|high", "mitigation": "...", "source_excerpt": "...", "page": 1 }}],
  "action_items": [{{ "description": "...", "owner": "...", "due_date": "...", "source_excerpt": "...", "page": 1 }}],
  "deadlines": [{{ "label": "...", "date": "...", "source_excerpt": "...", "page": 1 }}],
  "owners": [{{ "name": "...", "role": "...", "area": "...", "source_excerpt": "...", "page": 1 }}]
}}
"""

                content = call_llm(prompt, temperature=0.0, json_mode=True)
                extracted_data = json.loads(content)
                
                # Add a brief rate-limiting sleep between batches
                await asyncio.sleep(2.0)
                
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
                    if entity_type not in allowed_types:
                        continue
                    if not isinstance(items, list):
                        continue
                        
                    for item in items:
                        if not item:
                            continue
                        source_excerpt = item.pop("source_excerpt", "")
                        
                        # Extract and sanitize page
                        page_val = item.pop("page", 1)
                        try:
                            page_num = int(page_val)
                        except (ValueError, TypeError):
                            page_num = 1
                        item["page"] = page_num
                        
                        # Generate embedding for the entity JSON structure to enable pgvector searches
                        val_str = json.dumps(item)
                        entity_vector = get_embedding(val_str)
                        
                        db_entity = Entity(
                            document_id=doc_id,
                            type=entity_type,
                            value=item,
                            source_excerpt=source_excerpt,
                            embedding=entity_vector
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

# Node 3: Knowledge Merge (Comparing new entities with existing ones using pgvector cosine_distance)
async def knowledge_merge_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting knowledge merge node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "knowledge_merge")
        
        if not state["planner_decision"].get("requires_conflict_check", True):
            logger.info(f"[{run_id}] Skipping knowledge merge node as requested by the plan.")
            await update_job_node(db, run_id, "knowledge_merge", status="complete")
            state["conflicts"] = []
            return state

        new_entities = state["entities"]
        conflicts_to_check = []
        
        try:
            for new_ent in new_entities:
                new_type = new_ent["type"]
                new_val_str = json.dumps(new_ent["value"])
                new_vec = get_embedding(new_val_str)
                
                # Query existing entities of the same type NOT from the current document, isolated by workspace
                # Filter by cosine distance <= 0.60 (corresponds to cosine similarity >= 0.40)
                stmt = (
                    select(Entity)
                    .join(Document)
                    .where(Entity.document_id != doc_id)
                    .where(Document.workspace_id == state["workspace_id"])
                    .where(Entity.type == new_type)
                    .where(Entity.embedding.cosine_distance(new_vec) <= 0.60)
                    .order_by(Entity.embedding.cosine_distance(new_vec))
                )
                res = await db.execute(stmt)
                matching_entities = res.scalars().all()
                
                for ext_ent in matching_entities:
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
    
    # Mapping categories to sections
    category_to_sections = {
        "feature": ["Major Features"],
        "decision": ["Current Decisions", "Pending Decisions"],
        "component": ["Architecture"],
        "risk": ["Known Risks", "Open Questions"],
        "deadline": ["Timeline"],
        "owner": ["Project Overview"],
        "action_item": ["Project Overview", "Timeline"]
    }
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "conflict_detection")
        
        candidates = state["conflicts"]
        new_entities = state["entities"]
        detected_conflicts = []
        affected_sections = set()

        # Check if the plan requires a conflict check
        if not state["planner_decision"].get("requires_conflict_check", True) or not candidates:
            logger.info(f"[{run_id}] Skipping conflict detection node or no candidates found.")
            await update_job_node(db, run_id, "conflict_detection", status="complete")
            
            # If no conflicts checked, default to drafting all sections matching new entity types
            if not affected_sections:
                for new_ent in new_entities:
                    sections = category_to_sections.get(new_ent["type"], [])
                    for s in sections:
                        affected_sections.add(s)
            state["sections_to_draft"] = list(affected_sections)
            return state
        
        try:
            for item in candidates:
                new_ent = item["new_entity"]
                ext_ent = item["existing_entity"]
                
                # Check semantic conflict using LLM reasoning
                prompt = f"""You are an expert software project intelligence auditor. Compare these two project records of type '{new_ent['type']}'.
Determine if they have a flat logical contradiction (e.g. they specify conflicting timelines, contradicting system decisions, or directly opposing owners/features).

Record A:
- Excerpt: \"{ext_ent['source_excerpt']}\"
- Fact Details: {json.dumps(ext_ent['value'])}

Record B (New):
- Excerpt: \"{new_ent['source_excerpt']}\"
- Fact Details: {json.dumps(new_ent['value'])}

Response format:
You must respond with a raw JSON object only. Do not include markdown codeblocks or conversational text.
JSON structure:
{{
  "conflict": true | false,
  "category": "Reason category (e.g. Timelines, Component Ownership, Auth mechanism, etc)",
  "severity": "low | medium | high",
  "explanation": "State clearly why Record B contradicts Record A"
}}
"""
                content = call_llm(prompt, temperature=0.0, json_mode=True)
                audit = json.loads(content)
                
                if audit.get("conflict"):
                    db_conflict = Conflict(
                        workspace_id=state["workspace_id"],
                        category=audit.get("category", "General"),
                        description=audit.get("explanation", "Conflict detected"),
                        severity=audit.get("severity", "medium"),
                        existing_entity_id=UUID(ext_ent["id"]),
                        new_entity_id=UUID(new_ent["id"]),
                        resolved=False
                    )
                    db.add(db_conflict)
                    await db.flush() # Populate ID
                    
                    detected_conflicts.append({
                        "id": str(db_conflict.id),
                        "category": db_conflict.category,
                        "description": db_conflict.description,
                        "severity": db_conflict.severity
                    })
                    
                    # Mark sections affected by this category
                    sections = category_to_sections.get(new_ent["type"], [])
                    for s in sections:
                        affected_sections.add(s)
            
            # If no conflicts were found, we default to drafting all sections that match the new entity types
            if not affected_sections:
                for new_ent in new_entities:
                    sections = category_to_sections.get(new_ent["type"], [])
                    for s in sections:
                        affected_sections.add(s)
                        
            state["sections_to_draft"] = list(affected_sections)
            await db.commit()
            
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
        
        # 1. Filter sections based on planner's affected_sections
        planner_sections = state["planner_decision"].get("affected_sections", [])
        sections = [s for s in sections if s in planner_sections]
        
        # 2. Exclude Timeline if requires_timeline_update is False
        if not state["planner_decision"].get("requires_timeline_update", True):
            sections = [s for s in sections if s != "Timeline"]
            
        if not sections:
            logger.info(f"[{run_id}] No sections to draft based on planner decision.")
            await update_job_node(db, run_id, "generate_brief_updates", status="complete")
            return state
        
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
                # Join Document and eager-load it so we can access document name/id in prompt formatting
                ent_stmt = (
                    select(Entity)
                    .options(joinedload(Entity.document))
                    .join(Document)
                    .where(Entity.type.in_(ent_types))
                    .where(Document.workspace_id == state["workspace_id"])
                )
                ent_res = await db.execute(ent_stmt)
                all_entities = ent_res.scalars().all()
                
                entities_str = "\n".join([
                    f"- {ent.type.upper()}: {json.dumps(ent.value)} (Source Excerpt: \"{ent.source_excerpt}\", Document Name: '{ent.document.filename}', Document ID: {ent.document.id}, Page: {ent.value.get('page', 1)})"
                    for ent in all_entities
                ])
                
                # Ask LLM to draft the updated section content with strict grounding and citations
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

GROUNDING RULES:
1. Every claim, feature, tech decision, deadline, component, or item you add/update MUST be cited from the source facts.
2. For every claim, append a clickable citation link exactly in one of the following formats depending on the file:
   - For PDF documents or documents with a page number, use: Source: [Document Name · Page X](http://localhost:8000/documents/{{doc_id}}/download) where X is the page number from the corresponding 'Page' fact.
   - For other documents, use: Source: [Document Name](http://localhost:8000/documents/{{doc_id}}/download)
   Crucial: Do not wrap the citation in parentheses. Output exactly: Source: [Document Name · Page X](...) or Source: [Document Name](...).
3. STRICT HACK PREVENTION: Do not make up any facts, features, dates, owners, or decisions. If an item is not directly supported by a source fact excerpt, do not include it. Every bullet point or statement must have a citation.
4. Keep the style premium, high-level, and clean.
5. Do not add any introductory or concluding comments. Start directly with the updated Markdown content.
"""
                
                draft_content = call_llm(prompt, temperature=0.2, json_mode=False).strip()
                
                # Add a brief rate-limiting sleep between section drafts
                await asyncio.sleep(2.0)
                
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
        from backend.app.services.parser_service import extract_text_and_type, chunk_text
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
        "error": "",
        "planner_decision": {}
    }
    
    # Execute node state transitions
    state = await classification_node(state)
    if state.get("error"):
        return
        
    state = await planner_node(state)
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
        
    # Mark document status as complete
    async with async_session_maker() as db:
        stmt = (
            update(Document)
            .where(Document.id == state["document_id"])
            .values(status="complete")
        )
        await db.execute(stmt)
        await db.commit()
        
    logger.info(f"[{run_id}] Finished processing up to interrupt stage successfully.")
