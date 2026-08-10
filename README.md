# LiveBrief - Project Intelligence Agent

LiveBrief is a state-of-the-art agentic document intelligence system that automatically reconciles disparate, unstructured software engineering documents (such as PRDs, meeting notes, architecture designs, and ADRs) into a single, cohesive, living **Project Brief** source of truth.

The application leverages **local open-source sentence embeddings**, a **PostgreSQL Vector Database (pgvector)**, and **large language models (LLMs)** to automatically categorize documents, extract key structured entities (features, decisions, timelines), highlight structural contradictions, and recommend versioned brief updates for human approval.

---

## 🏗️ System Architecture & Data Flow

LiveBrief follows a clean, modular architectural layout separating route handlers, core state machines, vector processing utilities, and schema definitions.

### Component Architecture Diagram

```mermaid
graph TB
    subgraph Frontend ["React & Vite Frontend"]
        UI["Interactive Brief / Review Dashboard"]
    end

    subgraph Backend ["FastAPI Application Server"]
        R_Docs["Document Router"]
        R_Conf["Conflict Router"]
        R_Rev["Review Router"]
        R_Sum["Summary Router"]
        
        Parser["Parser Service"]
        Embedder["Embedding Service"]
        Agent["Agent Service"]
        Exporter["Export Service"]
    end

    subgraph DB ["PostgreSQL Vector Database"]
        Tables[("Relational Tables")]
        VectorIndex[("pgvector Embeddings Index")]
    end

    UI <-->|API Requests / JSON| Backend
    R_Docs -->|Trigger Job| Agent
    Agent -->|Extract Text & Chunk| Parser
    Agent -->|Compute Embeddings| Embedder
    Agent -->|CRUD Entities / Conflicts / Drafts| DB
    Embedder <-->|Local SentenceTransformer| VectorIndex
    Exporter -->|Build Document Briefs| DB
```

### Directory Structure

```text
backend/app/
├── core/
│   ├── config.py             # App configurations (ports, path mappings, model names)
│   └── database.py           # Async engine & session pool (SQLAlchemy + asyncpg)
├── models/
│   ├── __init__.py           # Model index
│   └── models.py             # SQLAlchemy models (Workspace, Document, Entity, Conflict, etc.)
├── schemas/
│   ├── __init__.py           # Schema index
│   └── schemas.py            # Pydantic schemas for API payload validation & serialization
├── services/
│   ├── __init__.py           # Service index
│   ├── agent_service.py      # Core agent state machine (Classification -> Brief Drafting)
│   ├── embedding_service.py  # Local MiniLM sentence embedder (384-dimension vector generation)
│   ├── export_service.py     # PDF & DOCX generator from project brief sections
│   └── parser_service.py     # Multi-format parser (.md, .pdf, .docx) & contextual chunker
└── routers/
    ├── __init__.py           # APIRouter index and registry
    ├── deps.py               # Shared API dependencies (e.g. Workspace extraction)
    ├── workspaces.py         # Workspace retrieval & template configuration
    ├── documents.py          # Document upload & ingestion trigger endpoints
    ├── project_summary.py    # Summary brief section management & exports
    ├── conflicts.py          # Conflict logs & details endpoints
    ├── reviews.py            # Recommended drafts approval/rejection endpoints
    ├── timeline.py           # Audit events & reverse chronological activity logs
    └── jobs.py               # Pipeline state & execution tracking endpoints
```

---

## 🧬 Agentic Pipeline Workflow

When a file is uploaded, a background task initiates a resumable state-transition pipeline through five distinct nodes (implemented as a LangGraph-like state flow):

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Router as API Router
    participant Agent as Agent Service
    participant DB as PostgreSQL
    participant LLM as Chat LLM

    User->>Router: Upload Document
    Router->>Agent: Run Agent Pipeline
    activate Agent
    
    rect rgb(240, 240, 240)
        note right of Agent: Node 1: Classification
        Agent->>LLM: Classify (First 3k chars)
        LLM-->>Agent: Type & Confidence JSON
        Agent->>DB: Update Document status & type
    end

    rect rgb(230, 240, 250)
        note right of Agent: Node 2: Information Extraction
        Agent->>Agent: Parse & Chunk Content
        Agent->>LLM: Extract structured facts
        LLM-->>Agent: Features, Decisions, Milestones, Owners
        Agent->>Agent: Generate identifying text embeddings
        Agent->>DB: Save Entities & Chunks
    end

    rect rgb(220, 240, 240)
        note right of Agent: Node 3: Knowledge Merge
        Agent->>DB: Query similar active entities in workspace (cosine similarity >= 0.40)
        DB-->>Agent: Matching existing entities
    end

    rect rgb(240, 240, 230)
        note right of Agent: Node 4: Conflict Detection
        Agent->>LLM: Compare matched pairs for contradictions
        LLM-->>Agent: Audit Results (Conflict status, explanation)
        Agent->>Agent: Deduplicate equivalent conflicts in batch
        Agent->>DB: Save detected Conflicts
    end

    rect rgb(240, 230, 240)
        note right of Agent: Node 5: Brief Drafting
        Agent->>DB: Fetch all active entities for affected sections
        Agent->>LLM: Draft updated Markdown content (Grounding/Citations)
        LLM-->>Agent: Section Draft Markdown
        Agent->>DB: Create Review Task (Status: pending)
    end

    Agent-->>Router: Job Pending Review
    deactivate Agent
    Router-->>User: Success response (Waiting for review)
```

---

## 🔍 Detailed Component Deep-Dive

### 1. Contextual Extraction & Embedding Strategy
Unlike naive RAG systems which embed whole raw paragraphs directly, LiveBrief extracts structured details first. The system:
- Isolates information into seven schema categories: `features`, `technical_decisions`, `components`, `risks`, `action_items`, `deadlines`, and `owners`.
- Generates vectors based on **identifying text** (e.g. decision title, feature name, milestone label) instead of stringified raw JSON or rationales. This ensures pgvector cosine distance matches entities strictly on *what they represent* rather than *why they were chosen* or *who owns them*.

### 2. High-Fidelity Conflict Auditor
The conflict detection node resolves false positives by performing a strict logical decision tree. 

Before flagging a pair of records as a conflict, it verifies:
```text
Same underlying entity/task/milestone/decision?
                     ↓ (Yes)
              Same attribute?
                     ↓ (Yes)
        Are the values actually incompatible?
                     ↓ (Yes)
Is this NOT merely missing information/new information/an update?
                     ↓ (Yes)
               [ CONFLICT ]
```

#### Resolved False Positive Scenarios
- **WebSocket chosen vs long polling rejected**: Recognized as complementary/compatible decisions.
- **Core v1 feature vs deferred feature**: Distinct features (e.g. Feat A in v1, Feat B in v1.1) are not conflicts.
- **Missing information**: The omission of a detail in one document is never treated as a contradiction.
- **Different milestones**: Sequential checkpoints (Internal Alpha, Closed Beta, Public Beta) are chronologically consistent.
- **Different tasks**: Different owners and deadlines are allowed for different tasks.
- **Open questions resolved later**: When an open question or pending decision in an older document is resolved in a newer document, it is classified as an update, not a contradiction.

### 3. Duplicate Conflict Deduplication
To prevent users from being overwhelmed by the same logical issue multiple times, candidate matches are grouped and deduplicated before insertion using a composite key: `(entity_type, existing_identifying_text, new_identifying_text)`. A single logical issue results in one conflict log finding.

### 4. Human-In-The-Loop Review Queue
Draft updates are never written directly to the project summary brief. Instead:
- proposed changes are saved as `Review` tasks.
- Committing updates requires explicit User approval via the `/review/{id}/approve` endpoint, which increments the version of the corresponding section in `project_summary` and appends an entry to the audit timeline.
- Citations are formatted cleanly (e.g., `Source: [Document Name · Page X]`) for strict traceability.

### 5. Incremental Project Brief Updates (Semantic Git Diffs)
To prevent unrelated brief sections from being modified by the LLM during drafting, LiveBrief implements an incremental, semantic diff-based drafting pipeline:
- **Planner Scoping**: The Planner node evaluates the input document and identifies only the sections that are affected.
- **Targeted Generation**: The system generates drafts **only** for these affected sections. Unaffected sections are copied directly from their latest database version without running through the LLM.
- **Semantic Diff Verification**: If the LLM-generated draft for an affected section matches the existing section content exactly, no review task is created, preventing unnecessary versions from being checked in.
- **Structured Diff Output**: Sections that change are classified as `add` or `modify` and stored in the review's `proposed_change` field with the following metadata:
  - `section`: Name of the section (e.g. `Timeline`).
  - `operation`: `add` or `modify`.
  - `old_value`: Current section content.
  - `new_value`: Drafted section content.
  - `reason`: Justification explaining the change.
  - `source_provenance`: Structured document name and pages citation.

### 6. Git-like Version Control & Section Rollbacks
Every change to a project brief section is fully versioned, allowing developer teams to review change histories and perform section rollbacks:
- **Database Versioning**: The `project_summary` table tracks sections individually. Approving an update inserts a new row with `version = latest_version + 1` rather than overwriting in-place.
- **Rollback API**: The `POST /project-summary/{section}/rollback?version={version_number}` endpoint fetches the target version, duplicates its content, and saves it as a new version entry while registering a `Timeline` event in the audit trail.
- **Interactive UI Rollback**: Older versions displayed in the "History" panel show a **Rollback** action button that instantly restores the brief section to that checkpoint.

---

## 🗄️ Database Entity-Relationship Diagram

LiveBrief utilizes a relational schema optimized with the `pgvector` extension for semantic search capabilities:

![ER Diagram](assets/er.png)

---

## 🤖 Model Context Protocol (MCP) Server

LiveBrief exposes its core agentic and document intelligence capabilities through an integrated Model Context Protocol (MCP) server. This allows external LLMs, AI agents, or developer clients (such as Cursor or Claude Desktop) to programmatically interact with LiveBrief workspaces, ingest documents, check pipeline runs, track conflicts, and resolve project brief updates.

### 🌐 MCP Transport
The LiveBrief MCP server supports two transport mechanisms:
1. **Server-Sent Events (SSE)** (Default for network access): Mounted directly on the FastAPI web server at `http://localhost:8000/mcp/sse`. This transport allows multiple external clients to connect concurrently over the network.
2. **Standard Input/Output (stdio)** (Default for local execution): Available by running the Python script directly.

### 🛠️ Exposed MCP Tools

The following tools are available to any connected MCP client:

| Tool Name | Arguments | Description | Output Schema |
|---|---|---|---|
| `create_workspace` | `name` (string) | Create a new workspace with default template sections. | `{"workspace_id": "...", "name": "..."}` |
| `list_workspaces` | None | List all available workspaces in the database. | Array of `{"workspace_id": "...", "name": "..."}` |
| `ingest_document` | `workspace_id` (string), `filename` (string), `content` (string) | Ingest a document and queue it for parsing and agent processing. | `{"document_id": "...", "run_id": "..."}` |
| `get_run_status` | `run_id` (string) | Retrieve execution details (status, node, planner decision, errors) of a job run. | `{"run_id": "...", "status": "...", "current_node": "...", "planner": {...}, "error": "..."}` |
| `get_project_brief` | `workspace_id` (string) | Retrieve current compiled brief sections, content, and version tracking. | Array of `{"section": "...", "version": 1, "content": "..."}` |
| `get_conflicts` | `workspace_id` (string) | Retrieve unresolved document conflicts and recommendations. | Array of `{"conflict_id": "...", "category": "...", "description": "...", "source_entities": {...}}` |
| `get_pending_reviews` | `workspace_id` (string) | Retrieve pending proposed changes waiting in the review queue. | Array of `{"review_id": "...", "proposed_change": {...}, "status": "pending"}` |
| `approve_review` | `review_id` (string) | Approve a pending review, committing recommendations to the brief. | `{"review_id": "...", "status": "approved", "brief_section": "...", "new_version": 2}` |
| `reject_review` | `review_id` (string), `rejection_reason` (string) | Reject and discard a proposed brief update. | `{"review_id": "...", "status": "rejected", "reason": "..."}` |
| `get_audit_trail` | `workspace_id` (string) | Retrieve chronological history/timeline of all workspace modifications. | Array of `{"timestamp": "...", "event": "...", "reason": "...", "actor": "..."}` |
| `resume_run` | `run_id` (string) | Resume and restart a failed GraphRun pipeline processing job. | `{"run_id": "...", "status": "running", "current_node": "upload"}` |

### 🚀 Starting the MCP Server

Since the MCP server is mounted directly into the FastAPI application, starting the backend web application automatically serves the MCP server over HTTP SSE:

```bash
# Start backend API (including MCP SSE server at /mcp/sse)
uv run uvicorn backend.app.main:app --reload --port 8000
```

To run the MCP server standalone in stdio mode:
```bash
uv run python -m backend.app.mcp_server
```

### 🔌 Connecting an MCP Client

#### 1. Connecting via SSE (Network/HTTP)
Configure your MCP client to connect to the SSE endpoint:
- **SSE URL**: `http://localhost:8000/mcp/sse`
- **Client Post URL**: `http://localhost:8000/mcp/messages`

#### 2. Connecting via Stdio (Local Process)
To configure local developer environments like **Cursor** or **Claude Desktop**, specify the local process command:

##### Cursor Configuration:
Go to **Settings** -> **Features** -> **MCP**, click **+ Add New MCP Server**, and set:
- **Name**: `LiveBrief`
- **Type**: `stdio`
- **Command**: `uv run python -m backend.app.mcp_server`
- **Execution Directory (Cwd)**: `C:/Projects/Python-projects/LiveBrief`

##### Claude Desktop Configuration (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "livebrief": {
      "command": "uv",
      "args": ["run", "python", "-m", "backend.app.mcp_server"],
      "cwd": "C:/Projects/Python-projects/LiveBrief"
    }
  }
}
```

### 🤖 Example: External Agent Calling LiveBrief
Below is an example of an external Python script using the `mcp` client SDK to list workspaces and ingest a document:

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def run_agent():
    async with sse_client("http://localhost:8000/mcp/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # 1. List available workspaces
            workspaces = await session.call_tool("list_workspaces")
            print("Workspaces:", workspaces.content[0].text)
            
            # 2. Ingest a document
            ingest_result = await session.call_tool("ingest_document", {
                "workspace_id": "your-workspace-uuid-here",
                "filename": "meeting_notes.md",
                "content": "# Product Meeting Notes\n* Authentication should use JWT tokens."
            })
            print("Ingest Result:", ingest_result.content[0].text)

asyncio.run(run_agent())
```

## 🐳 Docker Quickstart (Single-Command Setup)

You can spin up the entire LiveBrief stack (PostgreSQL with pgvector, FastAPI backend, and React frontend) with a single command.

### Prerequisites
Make sure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

### Steps
1. Create a `.env` file in the root directory and add your Groq API credentials:
   ```env
   GROQ_API_KEY=your-groq-api-key-here
   GROQ_MODEL=llama-3.1-8b-instant
   ```
2. Build and start all services:
   ```bash
   docker compose up --build
   ```

This command will:
- Start the PostgreSQL database and automatically initialize the schema and required extensions (`pgvector`).
- Build and run the FastAPI backend at `http://localhost:8000`.
- Build and run the React frontend dev server at `http://localhost:5173`.
- Auto-mount the MCP SSE server endpoint at `http://localhost:8000/mcp/sse`.

---

## 🛠️ Local Installation & Development

### 1. Database Setup
Start a PostgreSQL 16 container with `pgvector` installed:
```bash
docker run --name postgres -e POSTGRES_PASSWORD=1234 -e POSTGRES_USER=ammar -e POSTGRES_DB=livebrief -p 5432:5432 -d pgvector/pgvector:pg16
```

### 2. Backend Setup
1. Ensure Python 3.11+ is installed.
2. Configure environmental variables in a local `.env` file:
   ```env
   DATABASE_URL=postgresql+asyncpg://ammar:1234@localhost:5432/livebrief
   GROQ_API_KEY=your-groq-api-key
   GROQ_MODEL=llama3-70b-8192
   ```
3. Synchronize dependencies using `uv`:
   ```bash
   uv sync
   ```
4. Run table initialization:
   ```bash
   uv run python -m backend.app.init_db
   ```
5. Start the FastAPI backend server:
   ```bash
   uv run uvicorn backend.app.main:app --reload --port 8000
   ```

### 3. Frontend Setup
Navigate to the frontend directory and launch the Vite development server:
```bash
cd frontend
npm install
npm run dev
```

### 4. Running the Test Suite
To execute the mock and unit test suites:
```bash
uv run python -m pytest
```
