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

## ⚙️ Design Decisions, Architecture Choices & Trade-offs

LiveBrief is designed around a checkpoint-driven, modular pipeline where document ingestion runs as a background task. This section covers the architectural choices, trade-offs, system behavior on failures, and domain/format coverage.

### 🏛️ Component Architecture & Reason for Choice
We chose a **modular linear agent pipeline** over an orchestrator loop or generic graph library:
- **Atomic Node Duties**: Each stage (`classification`, `planner`, `extraction`, `knowledge_merge`, `conflict_detection`, `generate_brief_updates`) is implemented as an atomic async function in [agent_service.py](file:///c:/Projects/Python-projects/LiveBrief/backend/app/services/agent_service.py).
- **Persistent Database Checkpoints**: The database stores the run's `current_node` and execution `status`.
- **Reason for Choice**: It isolates complexity, makes tracing LLM calls straightforward, and allows us to implement node-level resumption without re-running the entire ingestion process if a step is interrupted or fails.

---

### ⚖️ Cost vs. Benefit Analysis (Trade-offs)

#### 1. Latency
- **What it buys us**: The Planner node scopes down the work by selecting only the affected brief sections. This prevents the system from re-drafting all sections, making the final drafting step significantly faster. Additionally, classification runs on only the first 3,000 characters, resolving doc type in milliseconds.
- **What it costs us**: The sequential execution of up to 6 distinct nodes (with LLM and embedding calls in each) creates a longer total execution path (20-40 seconds). Since this runs asynchronously in background tasks, it does not block the user API response.

#### 2. Money & API Token Optimization
- **What it buys us**: Scoping LLM generation strictly to affected sections and using a local, open-source sentence embedding model (`all-MiniLM-L6-v2`) keeps token costs extremely low. 
- **What it costs us**: Running multiple semantic audits and entity extraction batches requires multiple Groq API calls. If the model outputs very large payloads, it can hit rate limits on free-tier API keys. We resolved this by implementing rate-limit retries with backoff and setting a high `max_tokens=4096` limit.

#### 3. Simplicity
- **What it buys us**: A standard Python async workflow utilizing pure SQLAlchemy transactions is simple to understand, deploy, and debug. There is no need for external agent runtimes or graph databases.
- **What it costs us**: We had to build custom in-memory reconstruction logic and database serialization handlers to restore state correctly when resuming from a middle step.

#### 4. Room to Grow
- **What it buys us**: Clean node inputs and outputs make it trivial to plug in additional analysis steps (e.g., security checks, cost estimation, compliance checking) without modifying the existing architecture.
- **What it costs us**: Large-scale production deployments processing thousands of documents concurrently will need a robust task broker like Celery or RQ instead of FastAPI's lightweight `BackgroundTasks`.

---

### 🛡️ Behavior Under Failures & Recovery

#### 1. How the System Behaves When a Step Fails
- **Node Exception**: If an LLM call fails, the database connection drops, or validation errors occur during a node execution, the error is caught, saved to the `GraphRun.error` field, and the run is marked as `"failed"`.
- **Manual Resumption**: Using the `resume_run` tool, you can resume failed runs. The pipeline reads the failure checkpoint from the database and runs the failed node again—**completely skipping prior nodes** that already successfully completed.

#### 2. Container/Process Interruption (Killed Backend)
- **Automatic Recovery on Startup**: If the backend container or process is terminated mid-run, the database status remains `"running"`. On backend startup, the FastAPI `lifespan` manager detects incomplete runs, transitions them to `"interrupted/recoverable"`, and automatically queues background tasks to resume them.
- **Idempotency Protection (Working the Second Time)**: Running the pipeline a second time or resuming mid-way is guaranteed not to duplicate records or corrupt workspace state because each node deletes previously generated records before executing its logic:
  - `extraction` deletes existing document entities and chunk embeddings.
  - `conflict_detection` deletes existing conflicts associated with the document's entities.
  - `generate_brief_updates` deletes previously created pending reviews for that run.

---

### 📂 Declared Formats & Domains

#### Supported Document Formats
LiveBrief supports parsing and processing the following document types:
- **Markdown (`.md`)**
- **Portable Document Format (`.pdf`)**
- **Microsoft Word (`.docx`)**

#### Supported Domains
The system is built specifically for **Software Engineering & Project Management** documents. It expects and successfully processes:
- Product Requirement Documents (PRDs)
- Architecture & System Designs
- Architecture Decision Records (ADRs)
- Meeting Notes & Action Items
- Sprint Planning & Backlog Specs
- Release Notes & Changelogs
- API Specifications

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

### 6. In-Place Brief Updates & Timeline Audit Trail
Every update to a project brief section is tracked in the system audit trail:
- **In-Place Section Updates**: When a proposed update is approved in the review dashboard, the target section in `project_summary` is updated directly in-place with timestamp tracking (`updated_at`) and review linkage (`last_review_id`).
- **Audit Trail & Timeline**: Every brief modification, document ingestion, and decision resolution is logged as a distinct `Timeline` event, providing complete traceability and provenance across the lifecycle of the project.

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
