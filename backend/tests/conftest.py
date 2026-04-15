"""
Shared fixtures and test app for the RAG system API tests.

app.py mounts StaticFiles at import time, which fails when the frontend
directory does not exist in the test environment.  This module builds an
equivalent FastAPI app inline so tests never touch the real app module.
"""

import sys
import os

# Ensure backend package is importable regardless of where pytest is invoked.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from typing import List, Optional
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request / response models (mirrors app.py)
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Request model for course queries"""
    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for course queries"""
    answer: str
    sources: List[str]
    session_id: str


class CourseStats(BaseModel):
    """Response model for course statistics"""
    total_courses: int
    course_titles: List[str]


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def create_test_app(mock_rag) -> FastAPI:
    """
    Return a FastAPI instance with the same routes as app.py but backed by
    *mock_rag* instead of a real RAGSystem.  No static files are mounted.
    """
    app = FastAPI(title="Test RAG App")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag.session_manager.create_session()
            answer, sources = mock_rag.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "Course Materials RAG System"}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag_system():
    """
    MagicMock standing in for RAGSystem.

    Defaults:
      - session_manager.create_session() → "session_1"
      - query()                          → ("Test answer", ["Course A - Lesson 1"])
      - get_course_analytics()           → 2 courses
    """
    mock = MagicMock()
    mock.session_manager.create_session.return_value = "session_1"
    mock.query.return_value = ("Test answer", ["Course A - Lesson 1"])
    mock.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Course A", "Course B"],
    }
    return mock


@pytest.fixture
def test_client(mock_rag_system):
    """Synchronous TestClient backed by the test app and the mock RAG system."""
    app = create_test_app(mock_rag_system)
    with TestClient(app) as client:
        yield client
