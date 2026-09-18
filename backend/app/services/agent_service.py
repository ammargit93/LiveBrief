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

# Helper to call LLM using LangChain ChatGroq with rate-limiting retries
async def call_llm(prompt: str, temperature: float = 0.0, json_mode: bool = False) -> str:
    from langchain_groq import ChatGroq
    import re
    import asyncio
    
    max_retries = 6
    backoff_delay = 2.0
    
    if json_mode:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_tokens=4096
        ).bind(response_format={"type": "json_object"})
    else:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_tokens=4096
        )
        
    for attempt in range(max_retries):
        try:
            response = await llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            err_msg = str(e)
            
            # Handle Groq JSON mode validation failures by falling back to non-JSON mode
            is_json_error = "json_validate_failed" in err_msg.lower() or "failed to generate json" in err_msg.lower()
            if json_mode and is_json_error:
                logger.warning("JSON mode validation failed. Retrying without JSON mode constraint...")
                fallback_llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    groq_api_key=settings.GROQ_API_KEY,
                    temperature=temperature,
                    max_tokens=4096
                )
                try:
                    response = await fallback_llm.ainvoke(prompt)
                    return response.content
                except Exception as fallback_err:
                    logger.error(f"Fallback call without JSON mode failed: {fallback_err}")
                    raise fallback_err
                    
            is_rate_limit = "rate_limit" in err_msg.lower() or "429" in err_msg or "rate limit reached" in err_msg.lower()
            
            if is_rate_limit and attempt < max_retries - 1:
                match_ms = re.search(r"try again in (\d+(?:\.\d+)?)ms", err_msg, re.IGNORECASE)
                match_s = re.search(r"try again in (\d+(?:\.\d+)?)s", err_msg, re.IGNORECASE)
                match_m = re.search(r"try again in (\d+(?:\.\d+)?)m(?!s)", err_msg, re.IGNORECASE)
                
                if match_ms:
                    sleep_time = float(match_ms.group(1)) / 1000.0 + 0.5
                elif match_s:
                    sleep_time = float(match_s.group(1)) + 0.5
                elif match_m:
                    sleep_time = float(match_m.group(1)) * 60.0 + 0.5
                else:
                    match_any = re.search(r"try again in (\d+(?:\.\d+)?)", err_msg, re.IGNORECASE)
                    if match_any:
                        sleep_time = float(match_any.group(1)) + 0.5
                    else:
                        sleep_time = backoff_delay * (2 ** attempt)
                    
                logger.warning(f"Rate limit hit. Attempt {attempt + 1}/{max_retries}. Sleeping for {sleep_time:.2f}s before retrying...")
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"LLM call failed after {attempt + 1} attempts: {e}")
                raise e

def get_entity_identifying_text(entity_type: str, value: Dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return str(value)
    
    if entity_type == "feature":
        val = value.get("name")
    elif entity_type == "decision":
        val = value.get("decision")
    elif entity_type == "component":
        val = value.get("name")
    elif entity_type == "risk":
        val = value.get("description")
    elif entity_type == "action_item":
        val = value.get("description")
    elif entity_type == "deadline":
        val = value.get("label")
    elif entity_type == "owner":
        val = value.get("name")
    else:
        val = None
        
    if val and isinstance(val, str):
        return val.strip()
    return json.dumps(value)

def format_entity_value(entity_type: str, value: Dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return str(value)
        
    parts = []
    if entity_type == "feature":
        name = value.get("name")
        desc = value.get("description")
        if name:
            parts.append(f"Feature: {name}")
        if desc:
            parts.append(f"Description: {desc}")
            
    elif entity_type == "decision":
        decision = value.get("decision")
        rationale = value.get("rationale")
        status = value.get("status")
        if decision:
            parts.append(f"Decision: {decision}")
        if status:
            parts.append(f"Status: {status}")
        if rationale:
            parts.append(f"Rationale: {rationale}")
            
    elif entity_type == "component":
        name = value.get("name")
        desc = value.get("description")
        if name:
            parts.append(f"Component: {name}")
        if desc:
            parts.append(f"Description: {desc}")
            
    elif entity_type == "risk":
        desc = value.get("description")
        severity = value.get("severity")
        mitigation = value.get("mitigation")
        if desc:
            parts.append(f"Risk: {desc}")
        if severity:
            parts.append(f"Severity: {severity}")
        if mitigation:
            parts.append(f"Mitigation: {mitigation}")
            
    elif entity_type == "action_item":
        desc = value.get("description")
        owner = value.get("owner")
        due = value.get("due_date")
        if desc:
            parts.append(f"Action Item: {desc}")
        if owner:
            parts.append(f"Owner: {owner}")
        if due:
            parts.append(f"Due Date: {due}")
            
    elif entity_type == "deadline":
        label = value.get("label")
        date = value.get("date")
        if label:
            parts.append(f"Deadline: {label}")
        if date:
            parts.append(f"Date: {date}")
            
    elif entity_type == "owner":
        name = value.get("name")
        role = value.get("role")
        area = value.get("area")
        if name:
            parts.append(f"Owner: {name}")
        if role:
            parts.append(f"Role: {role}")
        if area:
            parts.append(f"Area: {area}")
            
    else:
        for k, v in value.items():
            if k != "page":
                parts.append(f"{k.capitalize()}: {v}")
                
    if not parts:
        return str(value)
        
    return ", ".join(parts)

def repair_truncated_json(s: str) -> str:
    s = s.strip()
    if not s:
        return "{}"
        
    in_string = False
    escape = False
    stack = []
    clean_chars = []
    
    for char in s:
        if escape:
            clean_chars.append(char)
            escape = False
            continue
            
        if char == '\\':
            clean_chars.append(char)
            escape = True
            continue
            
        if char == '"':
            in_string = not in_string
            clean_chars.append(char)
            continue
            
        if in_string:
            clean_chars.append(char)
            continue
            
        if char in ('{', '['):
            stack.append(char)
            clean_chars.append(char)
        elif char in ('}', ']'):
            if stack:
                last = stack[-1]
                if (char == '}' and last == '{') or (char == ']' and last == '['):
                    stack.pop()
            clean_chars.append(char)
        else:
            clean_chars.append(char)
            
    rebuilt = "".join(clean_chars)
    if in_string:
        rebuilt += '"'
        
    while stack:
        last = stack.pop()
        if last == '{':
            rebuilt += '}'
        elif last == '[':
            rebuilt += ']'
            
    return rebuilt

def parse_json_robust(text: str) -> dict:
    text = text.strip()
    
    # 1. Try raw json.loads
    try:
        return json.loads(text)
    except Exception:
        pass
        
    # 2. Try to find markdown json code blocks: ```json ... ```
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
            
    # 3. Try to find the first '{' and last '}'
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
            
    # 4. Try to repair truncated JSON
    cleaned = text
    while cleaned and cleaned[-1] in (',', ':', ' ', '\t', '\n', '\r'):
        cleaned = cleaned[:-1].strip()
        
    try:
        repaired = repair_truncated_json(cleaned)
        return json.loads(repaired)
    except Exception:
        pass
        
    # Try one more fallback by stripping after the last comma
    try:
        last_comma = cleaned.rfind(',')
        if last_comma != -1:
            repaired = repair_truncated_json(cleaned[:last_comma])
            return json.loads(repaired)
    except Exception:
        pass

    raise ValueError(f"Could not parse valid JSON from LLM response: {text[:200]}...")

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
async def update_job_node(db: AsyncSession, run_id: str, node_name: str, status: str = None, error: str = None, planner_decision: dict = None):
    if status is None:
        stmt = select(GraphRun.status).where(GraphRun.id == run_id)
        res = await db.execute(stmt)
        curr_status = res.scalar()
        if curr_status == "interrupted/recoverable":
            status = "interrupted/recoverable"
        else:
            status = "running"
            
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
            content = await call_llm(prompt, temperature=0.0, json_mode=True)
            data = parse_json_robust(content)
            
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
            await update_job_node(db, run_id, "classification", status="complete")
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
        stmt = (
            select(ProjectSummary)
            .where(ProjectSummary.workspace_id == state["workspace_id"])
            .distinct(ProjectSummary.section)
            .order_by(ProjectSummary.section, desc(ProjectSummary.updated_at))
        )
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
            content = await call_llm(prompt, temperature=0.0, json_mode=True)
            from backend.app.schemas.schemas import PlannerDecision
            decision = PlannerDecision.model_validate_json(content)
            
            # Save the decision to state and persist in DB
            state["planner_decision"] = decision.model_dump()
            await update_job_node(db, run_id, "planner", status="complete", planner_decision=decision.model_dump())
            
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
            await update_job_node(db, run_id, "planner", status="complete", planner_decision=fallback_decision.model_dump())
            
    return state

# Node 2: Information Extraction
async def extraction_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting extraction node")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "extraction")
        
        # Delete existing entities and embeddings for this document_id to make extraction idempotent
        from sqlalchemy import delete
        await db.execute(delete(Entity).where(Entity.document_id == doc_id))
        await db.execute(delete(Embedding).where(Embedding.document_id == doc_id))
        await db.flush()
        
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

                content = await call_llm(prompt, temperature=0.0, json_mode=True)
                extracted_data = parse_json_robust(content)
                
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
                        
                        # Generate embedding for the identifying text to enable accurate pgvector searches
                        identifying_text = get_entity_identifying_text(entity_type, item)
                        entity_vector = get_embedding(identifying_text)
                        
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
                
            await update_job_node(db, run_id, "extraction", status="complete")
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
                identifying_text = get_entity_identifying_text(new_type, new_ent["value"])
                new_vec = get_embedding(identifying_text)
                
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
            await update_job_node(db, run_id, "knowledge_merge", status="complete")
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
        
        # Delete existing conflicts for this run/document to make conflict detection idempotent
        from sqlalchemy import delete
        doc_id = UUID(state["document_id"])
        entity_ids_stmt = select(Entity.id).where(Entity.document_id == doc_id)
        entity_ids_res = await db.execute(entity_ids_stmt)
        entity_ids = entity_ids_res.scalars().all()
        if entity_ids:
            await db.execute(
                delete(Conflict).where(Conflict.new_entity_id.in_(entity_ids))
            )
        await db.flush()
        
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
            added_conflict_keys = set()
            # Batch candidates in groups of 5 to avoid token limits per minute (TPM)
            sub_batch_size = 5
            for i in range(0, len(candidates), sub_batch_size):
                batch_candidates = candidates[i : i + sub_batch_size]
                
                prompt = f"""You are an expert software project intelligence auditor. Compare the following pairs of project records (Record A is older/existing, Record B is newer) to determine if they contain a logical contradiction (i.e. a conflict).

CORE AUDIT FLOW:
For each pair, determine:
1. Do both records refer to the EXACT SAME underlying entity, task, milestone, or system decision? (If NO -> NOT a conflict)
2. Do they refer to the EXACT SAME attribute/detail of that entity/task/milestone/decision? (If NO -> NOT a conflict)
3. Are the values for that attribute actually incompatible/contradictory? (If NO -> NOT a conflict)
4. Is this NOT merely missing information, new information, or a later update/superseding decision? (If it IS missing/new/updated info -> NOT a conflict)
5. If YES to all, classify as conflict: true. Otherwise, conflict: false.

Do NOT flag the following as conflicts (set "conflict": false):
* WebSocket chosen vs long polling rejected: Choices to use one technology and reject/not use another (e.g. Record A chooses WebSocket, Record B rejects long polling) are compatible decisions.
* Missing information: One record mentioning a constraint or detail while the other does not mention it is NOT a conflict. Absence of a claim must never be interpreted as contradiction.
* Different milestones: Distinct chronological milestones (e.g., Internal Alpha Apr 10, Closed Beta May 1, Public Beta July 1) are consistent. Only flag dates as conflicting if they specify different dates for the EXACT SAME milestone.
* Different tasks: Different owners or dates are fine for different tasks. Only flag a conflict after confirming the underlying task is the exact same.
* Open question/pending decision -> later decision: If an earlier record says something is an open question or pending, and a later record resolves it with a decision, this is an update/resolution, NOT a conflict.

If uncertain, prefer "conflict": false.

Pairs to audit:
"""
                for idx, item in enumerate(batch_candidates):
                    new_ent = item["new_entity"]
                    ext_ent = item["existing_entity"]
                    prompt += f"""
--- Pair #{idx+1} ---
Record A (Existing):
- ID: {ext_ent['id']}
- Excerpt: "{ext_ent['source_excerpt']}"
- Fact Details: {json.dumps(ext_ent['value'])}

Record B (New):
- ID: {new_ent['id']}
- Excerpt: "{new_ent['source_excerpt']}"
- Fact Details: {json.dumps(new_ent['value'])}
"""
                prompt += """
Response format:
You must respond with a raw JSON object only. Do not include markdown codeblocks or conversational text.
JSON structure:
{
  "audits": [
    {
      "existing_id": "ID of Record A",
      "new_id": "ID of Record B",
      "conflict": true | false,
      "category": "Reason category (e.g. Timelines, Component Ownership, Auth mechanism, etc)",
      "severity": "low | medium | high",
      "explanation": "State the relationship clearly. If it is a conflict, describe why they contradict (e.g., 'Both records refer to Closed Beta but specify different dates.'). If not a conflict, describe why they are compatible/updated/new (e.g., 'Record A chooses WebSocket while Record B rejects long polling; these are compatible decisions.', 'Record B adds information not present in Record A.', or 'Record B supersedes the earlier decision.')."
    }
  ]
}
"""
                try:
                    content = await call_llm(prompt, temperature=0.0, json_mode=True)
                    audit_data = parse_json_robust(content)
                    audits = audit_data.get("audits", [])
                except Exception as audit_err:
                    logger.error(f"Audit batch LLM call failed: {audit_err}")
                    audits = []
                    
                audits_map = {(a.get("existing_id"), a.get("new_id")): a for a in audits}
                
                for item in batch_candidates:
                    new_ent = item["new_entity"]
                    ext_ent = item["existing_entity"]
                    
                    audit = audits_map.get((str(ext_ent["id"]), str(new_ent["id"])))
                    if not audit:
                        audit = {"conflict": False}
                        
                    if audit.get("conflict"):
                        existing_identifying_text = get_entity_identifying_text(ext_ent["type"], ext_ent["value"]).lower()
                        new_identifying_text = get_entity_identifying_text(new_ent["type"], new_ent["value"]).lower()
                        conflict_key = (new_ent["type"], existing_identifying_text, new_identifying_text)
                        
                        if conflict_key not in added_conflict_keys:
                            added_conflict_keys.add(conflict_key)
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
                            
                # Sleep briefly between sub-batches to be kind to Groq rate limits
                if i + sub_batch_size < len(candidates):
                    await asyncio.sleep(2.0)
            
            # If no conflicts were found, we default to drafting all sections that match the new entity types
            if not affected_sections:
                for new_ent in new_entities:
                    sections = category_to_sections.get(new_ent["type"], [])
                    for s in sections:
                        affected_sections.add(s)
                        
            state["sections_to_draft"] = list(affected_sections)
            await update_job_node(db, run_id, "conflict_detection", status="complete")
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error in conflict detection: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "conflict_detection", status="failed", error=str(e))
            
    return state

def format_citations_deterministically(text: str) -> str:
    import re
    # Strip any existing Citations section at the bottom of the LLM draft
    text = re.sub(r'\n+\s*(?:#+\s*)?Citations.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Match square brackets or parentheses containing a filename with extension
    pattern = r'(?:Source:\s*)?\[([^\]]*\.(?:md|pdf|docx)[^\]]*)\]|(?:Source:\s*)?\(([^)]*\.(?:md|pdf|docx)[^)]*)\)'
    
    # 1. Find all raw matches to construct the unique list
    matches = re.findall(pattern, text, re.IGNORECASE)
    raw_citations = []
    for m in matches:
        c = next((item for item in m if item), "").strip()
        if c:
            if c.lower().startswith("source:"):
                c = c[7:].strip()
            c = c.replace('[', '').replace(']', '').replace('(', '').replace(')', '').strip()
            raw_citations.append(c)
            
    # 2. Build unique citations list preserving order
    unique_citations = []
    for c in raw_citations:
        c_clean = c.replace(' · ', ' ').replace(' - ', ' ').strip()
        c_clean = c_clean.strip(',. ')
        if c_clean and c_clean not in unique_citations:
            unique_citations.append(c_clean)
            
    # 3. Replace each citation in the text with its index
    def replace_callback(match):
        m = match.groups()
        c = next((item for item in m if item), "").strip()
        if not c:
            return ""
        if c.lower().startswith("source:"):
            c = c[7:].strip()
        c = c.replace('[', '').replace(']', '').replace('(', '').replace(')', '').strip()
        c_clean = c.replace(' · ', ' ').replace(' - ', ' ').strip().strip(',. ')
        if c_clean in unique_citations:
            idx = unique_citations.index(c_clean) + 1
            return f"({idx})"
        return ""
        
    new_text = re.sub(pattern, replace_callback, text, flags=re.IGNORECASE)
    
    # 4. Clean up any empty parentheses or trailing punctuation around citations
    new_text = new_text.replace('((', '(').replace('))', ')')
    new_text = re.sub(r'\s+\((\d+)\)', r' (\1)', new_text)
    
    # 5. Merge adjacent citation numbers like (1)(2) into (1,2)
    for _ in range(3):
        new_text = re.sub(r'\((\d+(?:,\d+)*)\)\s*\((\d+)\)', r'(\1,\2)', new_text)
        
    # 6. Append the Citations list at the bottom of the section
    if unique_citations:
        citations_block = "\n\n### Citations\n"
        for idx, cit in enumerate(unique_citations, 1):
            citations_block += f"{idx}) {cit}\n"
        new_text = new_text.rstrip() + citations_block
        
    return new_text

# Node 5: Generate Project Brief Updates (Incremental Diff System)
async def generate_brief_updates_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    doc_id = state["document_id"]
    logger.info(f"[{run_id}] Starting generate brief updates node (incremental diff system)")
    
    async with async_session_maker() as db:
        await update_job_node(db, run_id, "generate_brief_updates")
        
        # Delete existing pending reviews for this run to make it idempotent
        stmt = (
            select(Review)
            .where(Review.workspace_id == state["workspace_id"])
            .where(Review.status == "pending")
        )
        res = await db.execute(stmt)
        for r in res.scalars().all():
            if r.proposed_change.get("run_id") == str(run_id):
                await db.delete(r)
        await db.flush()
        
        # 1. The Planner determines affected sections
        sections = list(set(state["planner_decision"].get("affected_sections", [])))
        
        # 2. Exclude Timeline if requires_timeline_update is False
        if not state["planner_decision"].get("requires_timeline_update", True):
            sections = [s for s in sections if s != "Timeline"]
            
        if not sections:
            logger.info(f"[{run_id}] No affected sections to draft based on planner decision.")
            await update_job_node(db, run_id, "generate_brief_updates", status="complete")
            return state
            
        try:
            doc = await db.get(Document, doc_id)
            doc_name = doc.filename if doc else "Document"
            
            reviews_created = False
            
            for section_name in sections:
                # Fetch the current content of this section
                stmt = (
                    select(ProjectSummary)
                    .where(ProjectSummary.workspace_id == state["workspace_id"])
                    .where(ProjectSummary.section == section_name)
                )
                res = await db.execute(stmt)
                summary_section = res.scalars().first()
                existing_content = summary_section.content if summary_section else "(This section is currently empty.)"
                
                # Collect entities belonging to this section category
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
                
                # Fetch workspace entities of these types
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
                    f"- {ent.type.upper()}: {format_entity_value(ent.type, ent.value)} (Source Excerpt: \"{ent.source_excerpt}\", Document Name: '{ent.document.filename}', Document ID: {ent.document.id}, Page: {ent.value.get('page', 1)})"
                    for ent in all_entities
                ])
                
                prompt = f"""You are a professional technical writer and system architect. Update the Section '{section_name}' of our software project brief.
Here is the current content of Section '{section_name}':
\"\"\"
{existing_content}
\"\"\"

Here are the extracted structured facts and decisions we must incorporate (both existing and new updates):
\"\"\"
{entities_str}
\"\"\"

Please draft an updated Markdown version of Section '{section_name}', provide a brief reason for the change, and list the source provenance (document names and page numbers).

 GROUNDING RULES:
1. Every claim, feature, tech decision, deadline, component, or item you add/update MUST be cited from the source facts.
2. For every claim, append an inline citation exactly in one of the following formats:
   - For PDF documents or documents with a page number, use: Source: [Document Name · Page X] where X is the page number from the corresponding 'Page' fact.
   - For other documents, use: Source: [Document Name]
   Crucial: Output exactly: Source: [Document Name · Page X] or Source: [Document Name]. Do not include any URL links or parentheses containing a URL.
3. STRICT HACK PREVENTION: Do not make up any facts, features, dates, owners, or decisions. If an item is not directly supported by a source fact excerpt, do not include it. Every bullet point or statement must have a citation.
4. Keep the style premium, high-level, and clean.
5. Do NOT output a 'Citations' list section at the bottom. Start drafting the text directly.

You must respond with a JSON object matching this schema:
{{
  "new_value": "The complete updated Markdown content of the section, fully incorporating the facts, with inline citations (e.g. Source: [Document Name · Page X]). Do not include a Citations list at the bottom.",
  "reason": "A brief, clear explanation of what changed in this section and why (e.g. 'Timeline updated to October to reflect release delay').",
  "source_provenance": "A concise comma-separated list of the source documents and pages supporting this update."
}}
"""
                
                content = await call_llm(prompt, temperature=0.2, json_mode=True)
                draft_data = parse_json_robust(content)
                raw_draft_content = draft_data.get("new_value", "").strip()
                
                # Format citations deterministically (deduplicated index footnote style)
                draft_content = format_citations_deterministically(raw_draft_content)
                
                reason = draft_data.get("reason", "").strip()
                source_provenance = draft_data.get("source_provenance", "").strip()
                
                # Semantic Git Diff Check: Skip review if no content changes
                if draft_content.strip() == existing_content.strip():
                    logger.info(f"[{run_id}] Section '{section_name}' has no changes. Skipping review creation.")
                    continue
                    
                # Find if there is a linked conflict for this run
                conflict_id = None
                new_ent_ids = [UUID(ent["id"]) for ent in state["entities"]]
                if new_ent_ids:
                    conf_stmt = (
                        select(Conflict)
                        .where(Conflict.workspace_id == state["workspace_id"])
                        .where(Conflict.new_entity_id.in_(new_ent_ids))
                        .limit(1)
                    )
                    conf_res = await db.execute(conf_stmt)
                    conf_item = conf_res.scalars().first()
                    if conf_item:
                        conflict_id = conf_item.id
                        
                # Create a pending Review row
                proposed_change = {
                    "section": section_name,
                    "target_section": section_name,
                    "operation": "add" if (not existing_content or existing_content.startswith("(This section")) else "modify",
                    "old_value": existing_content,
                    "new_value": draft_content,
                    "reason": reason if reason else f"New details reconciled from {doc_name}",
                    "source_provenance": source_provenance if source_provenance else doc_name,
                    "source_document": doc_name,
                    "run_id": str(run_id),
                    "document_id": str(doc_id)
                }
                
                db_review = Review(
                    workspace_id=state["workspace_id"],
                    proposed_change=proposed_change,
                    conflict_id=conflict_id,
                    status="pending"
                )
                db.add(db_review)
                reviews_created = True
                
            if reviews_created:
                await update_job_node(db, run_id, "generate_brief_updates", status="waiting_for_review")
            else:
                logger.info(f"[{run_id}] No changes detected in any affected sections.")
                await update_job_node(db, run_id, "generate_brief_updates", status="complete")
                
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error in brief updates node: {e}")
            state["error"] = str(e)
            await update_job_node(db, run_id, "generate_brief_updates", status="failed", error=str(e))
            
    return state
            
    return state

# Full pipeline execution helper (LangGraph-like state transition)
# Helper to populate conflicts for state reconstruction when starting at conflict_detection
async def populate_conflicts_in_state(db: AsyncSession, state: AgentState) -> List[Dict[str, Any]]:
    if not state["planner_decision"].get("requires_conflict_check", True):
        return []
        
    new_entities = state["entities"]
    conflicts_to_check = []
    
    for new_ent in new_entities:
        new_type = new_ent["type"]
        identifying_text = get_entity_identifying_text(new_type, new_ent["value"])
        new_vec = get_embedding(identifying_text)
        
        stmt = (
            select(Entity)
            .join(Document)
            .where(Entity.document_id != UUID(state["document_id"]))
            .where(Document.workspace_id == UUID(state["workspace_id"]))
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
            
    return conflicts_to_check

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

    # Determine starting node
    node_sequence = [
        "upload",
        "classification",
        "planner",
        "extraction",
        "knowledge_merge",
        "conflict_detection",
        "generate_brief_updates",
    ]
    
    current_node = run.current_node
    current_status = run.status
    
    if current_node not in node_sequence:
        start_node = "classification"
    else:
        node_idx = node_sequence.index(current_node)
        if current_status in ["complete", "waiting_for_review"]:
            if node_idx + 1 < len(node_sequence):
                start_node = node_sequence[node_idx + 1]
            else:
                logger.info(f"[{run_id}] Run is already completed/waiting_for_review. Skipping execution.")
                return
        else:
            start_node = current_node
            
    if start_node == "upload":
        start_node = "classification"

    logger.info(f"[{run_id}] Resuming/Starting pipeline from node: {start_node}")

    # Build initial state
    state: AgentState = {
        "workspace_id": str(run.workspace_id),
        "document_id": str(doc.id),
        "run_id": str(run_id),
        "batch_id": str(run.batch_id),
        "filepath": doc.storage_path,
        "filename": doc.filename,
        "content": content,
        "chunks": chunks,
        "type": doc.type or "Unknown",
        "confidence": doc.classification_confidence or 0.0,
        "reasoning": "",
        "entities": [],
        "conflicts": [],
        "sections_to_draft": [],
        "error": "",
        "planner_decision": run.planner_decision or {}
    }

    # Load entities/conflicts if we are starting at/after knowledge_merge
    if start_node in ["knowledge_merge", "conflict_detection", "generate_brief_updates"]:
        async with async_session_maker() as db:
            ent_stmt = select(Entity).where(Entity.document_id == doc.id)
            ent_res = await db.execute(ent_stmt)
            db_entities = ent_res.scalars().all()
            state["entities"] = [
                {
                    "id": str(ent.id),
                    "document_id": str(ent.document_id),
                    "type": ent.type,
                    "value": ent.value,
                    "source_excerpt": ent.source_excerpt
                }
                for ent in db_entities
            ]
            
            if start_node == "conflict_detection":
                state["conflicts"] = await populate_conflicts_in_state(db, state)

    # Execute node state transitions starting from start_node
    if start_node == "classification":
        state = await classification_node(state)
        if state.get("error"):
            return
        start_node = "planner"

    if start_node == "planner":
        state = await planner_node(state)
        if state.get("error"):
            return
        start_node = "extraction"

    if start_node == "extraction":
        state = await extraction_node(state)
        if state.get("error"):
            return
        start_node = "knowledge_merge"

    if start_node == "knowledge_merge":
        state = await knowledge_merge_node(state)
        if state.get("error"):
            return
        start_node = "conflict_detection"

    if start_node == "conflict_detection":
        state = await conflict_detection_node(state)
        if state.get("error"):
            return
        start_node = "generate_brief_updates"

    if start_node == "generate_brief_updates":
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
        
    logger.info(f"[{run_id}] Finished processing pipeline successfully.")
