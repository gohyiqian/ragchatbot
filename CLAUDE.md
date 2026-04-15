# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A RAG (Retrieval-Augmented Generation) chatbot for querying course content. Uses ChromaDB for vector storage, Claude API for generation, and FastAPI for the backend. The frontend is plain HTML/JS/CSS.

## Setup & Running

Requires `uv` for package management and Python 3.13+.

```bash
# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env

# Run the application
./run.sh
# or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

App runs at `http://localhost:8000`. The FastAPI startup event auto-loads course documents from a `docs/` folder (in the `backend/` working directory).

## Architecture

### Backend (`backend/`)

The system is orchestrated by `rag_system.py`, which wires together:

- **`document_processor.py`** — Parses `.txt`/`.pdf`/`.docx` course files into `CourseChunk` objects. Documents must follow the format: first 3 lines are `Course Title:`, `Course Link:`, `Course Instructor:`, followed by `Lesson N: Title` sections.
- **`vector_store.py`** — ChromaDB wrapper with two collections: `course_catalog` (course-level metadata) and `course_content` (chunked text). Uses `all-MiniLM-L6-v2` for embeddings. Persists to `backend/chroma_db/`.
- **`ai_generator.py`** — Calls Claude (`claude-sonnet-4-20250514`) with an agentic tool-use loop. Claude is instructed to use the search tool for course-specific questions before answering.
- **`search_tools.py`** — Defines the `search_course_content` tool schema (Anthropic format) and `ToolManager` for dispatch. Tool accepts `query`, optional `course_name`, and optional `lesson_number`.
- **`session_manager.py`** — In-memory conversation history, max 10 messages per session, passed to Claude as context. `MAX_HISTORY=2` in config controls how many prior exchanges are included.
- **`app.py`** — FastAPI app, serves frontend static files from `../frontend`, exposes `POST /api/query` and `GET /api/courses`.

### Data Flow

```
User query → POST /api/query
  → RAGSystem.query()
    → AIGenerator: Claude API call with tool loop
      → ToolManager executes search_course_content
        → VectorStore.search() → ChromaDB semantic search
      → Claude generates answer using retrieved chunks
  → Response with answer + sources
```

### Frontend (`frontend/`)

Static files served by FastAPI. `script.js` manages session IDs, sends queries to `/api/query`, renders markdown responses (via `marked.js` CDN), and shows collapsible source attributions.

## Key Configuration (`backend/config.py`)

| Setting | Default | Purpose |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `CHUNK_SIZE` | 800 | Characters per chunk |
| `CHUNK_OVERLAP` | 100 | Overlap between chunks |
| `MAX_RESULTS` | 5 | Vector search results returned |
| `MAX_HISTORY` | 2 | Prior conversation turns sent to Claude |

## Adding Course Documents

Place `.txt` files in `backend/docs/` following this format:
```
Course Title: My Course
Course Link: https://...
Course Instructor: Name

Lesson 0: Introduction
Lesson Link: https://...
[content...]

Lesson 1: Next Topic
[content...]
```

The RAG system auto-loads all documents in `docs/` at startup. To reload, restart the server (ChromaDB persists to disk; duplicates are handled by upsert on `chunk_id`).
