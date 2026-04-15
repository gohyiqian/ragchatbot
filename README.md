# Course Materials RAG System

A Retrieval-Augmented Generation (RAG) system designed to answer questions about course materials using semantic search and AI-powered responses.

## Overview

This application is a full-stack web application that enables users to query course materials and receive intelligent, context-aware responses. It uses ChromaDB for vector storage, Anthropic's Claude for AI generation, and provides a web interface for interaction.

## Prerequisites

- Python 3.13 or higher
- uv (Python package manager)
- An Anthropic API key (for Claude AI)
- **For Windows**: Use Git Bash to run the application commands - [Download Git for Windows](https://git-scm.com/downloads/win)

## Installation

1. **Install uv** (if not already installed)

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Python dependencies**

   ```bash
   uv sync
   ```

3. **Set up environment variables**

   Create a `.env` file in the root directory:

   ```bash
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

## Running the Application

### Quick Start

Use the provided shell script:

```bash
chmod +x run.sh
./run.sh
```

### Manual Start

```bash
cd backend
uv run uvicorn app:app --reload --port 8000
```

The application will be available at:

- Web Interface: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs`

## Query Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          BROWSER (frontend)                         │
│                                                                     │
│   User types query → sendMessage()                                  │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  fetch POST /api/query                                      │   │
│   │  { query: "...", session_id: "session_1" | null }           │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                      │
│        show loading spinner  │        render markdown + sources     │
│              ↓               │               ↑                      │
└─────────────────────────────────────────────────────────────────────┘
                               │ HTTP POST           ↑ JSON response
                               ▼                     │
┌─────────────────────────────────────────────────────────────────────┐
│                        app.py  (FastAPI)                            │
│                                                                     │
│   if no session_id → session_manager.create_session()               │
│                                                                     │
│   answer, sources = rag_system.query(query, session_id)    ─────────┼──┐
│                                                                     │  │
│   return QueryResponse(answer, sources, session_id)        ◄────────┼──┘
└─────────────────────────────────────────────────────────────────────┘
                               │                     ↑
                               ▼                     │
┌─────────────────────────────────────────────────────────────────────┐
│                      rag_system.py  (RAGSystem)                     │
│                                                                     │
│  ① session_manager.get_conversation_history(session_id)             │
│    → "User: ...\nAssistant: ..." (or None for first message)        │
│                                                                     │
│  ② ai_generator.generate_response(query, history, tools) ───────┐   │
│                                                         ◄───────┘   │
│  ③ tool_manager.get_last_sources()  → ["Course - Lesson N", ...]    │
│     tool_manager.reset_sources()                                    │
│                                                                     │
│  ④ session_manager.add_exchange(session_id, query, response)        │
│    (trims to last MAX_HISTORY×2 = 4 messages)                       │
└─────────────────────────────────────────────────────────────────────┘
                               │                     ↑
                               ▼                     │
┌─────────────────────────────────────────────────────────────────────┐
│                    ai_generator.py  (AIGenerator)                   │
│                                                                     │
│   system = SYSTEM_PROMPT [+ conversation history if exists]         │
│   messages = [{ role: "user", content: query }]                     │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Claude API call #1   (tools attached, tool_choice: auto)   │   │
│   └──────────────────┬──────────────────────────────────────────┘   │
│                      │                                              │
│          ┌───────────┴────────────┐                                 │
│          │                        │                                 │
│   stop_reason=                stop_reason=                          │
│   "end_turn"                  "tool_use"                            │
│          │                        │                                 │
│          │              append assistant tool_use block             │
│          │              execute each tool call ──────────────────┐  │
│          │              append tool_result block  ◄──────────────┘  │
│          │                        │                                 │
│          │              ┌─────────┴──────────────────────────────┐  │
│          │              │  Claude API call #2  (no tools)        │  │
│          │              └─────────┬──────────────────────────────┘  │
│          │                        │                                 │
│          └───────────┬────────────┘                                 │
│                      ▼                                              │
│               return answer text                                    │
└─────────────────────────────────────────────────────────────────────┘
                               │ tool call           ↑ formatted chunks
                               ▼                     │
┌─────────────────────────────────────────────────────────────────────┐
│              search_tools.py  (ToolManager / CourseSearchTool)      │
│                                                                     │
│   tool_manager.execute_tool("search_course_content",                │
│     query, course_name?, lesson_number?)                            │
│          │                                                          │
│          ▼                                                          │
│   vector_store.search(query, course_name, lesson_number)            │
│          │                                                          │
│          ▼                                                          │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │  ChromaDB  (chroma_db/)                                      │  │
│   │  collection: course_content                                  │  │
│   │  embeddings: all-MiniLM-L6-v2                                │  │
│   │  → top MAX_RESULTS=5 chunks by cosine similarity             │  │
│   └──────────────────────────────────────────────────────────────┘  │
│          │                                                          │
│          ▼                                                          │
│   format: "[Course Title - Lesson N]\n<chunk text>"                 │
│   store sources in CourseSearchTool.last_sources                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Prompt to use

```
The chat interface displays query responses with source citations. I need to modify it so each source becomes a clickable
  link that opens the corresponding lesson video in a new tab:
  - When courses are processed into chunks in @backend/document_processor.py, the link of each lesson is stored in the
  course_catalog collection
  - Modify _format_results in @backend/search_tools.py so that the lesson links area also returned
  - The links should be embedded invisibly (no visible URL text)
```

```
 Add a '+ NEW CHAT' button to the left sidebar above the courses section. When clicked, it should:
  - Clear the current conversation in the chat window
  - Start a new session without page reload
  - Handle proper clean up on both @frontend and @backend
  - Match the styling of existing sections (Courses, Try asking) - same font size, color and uppercase formatting
```

```
Using the playwright MCP server visit http://127.0.0.1:8000 and view the new chat button. I want that button to look the same as the other links below for Courses and Try Asking. Make sure this is left aligned and that the border is removed
```

## Add MCP server

```
claude mcp add playwright npx @playwright/mcp@latest
```
