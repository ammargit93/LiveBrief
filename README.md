# LiveBrief - Project Intelligence Agent

LiveBrief is an agentic document intelligence system that reconciles software engineering documents (PRDs, meeting notes, architecture designs, ADRs) into a unified, living **Project Brief** source of truth. 

The application utilizes local semantic embeddings and large language models (LLMs) to automatically categorize documents, extract key features/decisions/timelines, highlight structural contradictions, and recommend versioned brief updates for human approval.

---

## 🛠️ Technology Stack

### Backend
* **FastAPI**: Asynchronous Python web framework for clean, high-performance REST APIs.
* **LangGraph**: Workflow orchestrator defining the document processing pipeline nodes (Classification -> Fact Extraction -> Merge -> Conflict Check -> Brief Drafts).
* **SQLAlchemy (Async)**: Modern ORM mapping Python structures to PostgreSQL tables with async pg database connection pooling.
* **Groq API (`llama-3.1-8b-instant`)**: High-performance LLM provider offering lightning-fast text processing and structured JSON outputs.
* **Local Semantic Embedder**: A customized bag-of-words / frequency embedding engine (50-dimension vector space) calculating cosine similarities locally.
* **ReportLab & python-docx**: Programmatic document generators exporting briefs to beautifully formatted PDF and Word (DOCX) formats.
* **PyPDF & python-docx Parsers**: Text extraction engines supporting `.md`, `.pdf`, and `.docx` document formats.

### Frontend
* **React (TypeScript)**: Single Page Application built on modern component architecture.
* **Vite**: Rapid-bundling development server.
* **Tailwind CSS (via CDN)**: Clean utility-first styling.
* **Lucide Icons**: Professional clean SVG micro-graphics interface icons.
* **Glassmorphism Light Theme**: Professional, high-contrast light-mode corporate visual layout with sharp corners (`rounded-none`).

---

## 🌟 Core Features

1. **Workspace Environments**
   * Create separate workspace profiles for different projects.
   * Isolates all documents, summaries, reviews, conflicts, and pipeline runs inside each workspace.

2. **Ingestion & Classification**
   * Batch-upload files in Markdown (`.md`), Word (`.docx`), or PDF (`.pdf`) formats.
   * Auto-classification of document types (e.g., PRD, Meeting Notes, Architecture Doc, ADR) with confidence scores.
   * Streamed file chunking (1MB buffers) and batched LLM fact extraction to handle large files (> 5MB).

3. **Living Project Brief**
   * A structured source of truth organized into 8 standard categories (Overview, Architecture, Major Features, Current Decisions, Known Risks, Pending Decisions, Open Questions, Timeline).
   * Fully version-controlled: each approved update inserts a new row in the database, preserving previous versions.
   * Clickable **History** logs showing timestamps and past content of each section.

4. **Review Recommendation Queue**
   * When new documents are ingested, proposed drafts are sent to a pending queue instead of modifying the brief directly.
   * High-contrast split-screen comparison showing **Current Text** vs. **Proposed Text**.
   * One-click action to **Approve** (merge changes into brief) or **Reject** (requiring a text reason).

5. **Conflict Flagging**
   * Scans similarities between incoming documents and active records.
   * Automatically alerts operators if contradiction details are found (e.g., one document specifying JWT authentication and another sync note specifying OAuth).

6. **Ingestion Pipeline Jobs Visualizer**
   * Real-time job state tracker displaying the active pipeline node (Upload -> Classification -> Extraction -> Merge -> Conflict Check -> Draft Brief).

7. **Timeline Audit Log**
   * An immutable, reverse-chronological event log recording all operator uploads, review approvals, and rejections with reasons.

8. **Brief Exports**
   * Download the entire compiled brief as a professional PDF or Word (DOCX) document instantly.
