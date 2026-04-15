"""
API endpoint tests for the RAG system.

Covered endpoints
-----------------
POST /api/query   – query_documents
GET  /api/courses – get_course_stats
GET  /            – root health check

All tests use the TestClient and mock_rag_system fixtures from conftest.py.
No real RAGSystem, ChromaDB, or Anthropic API calls are made.
"""

import pytest


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:

    def test_successful_query_returns_expected_fields(self, test_client, mock_rag_system):
        """A well-formed query returns answer, sources, and session_id."""
        mock_rag_system.query.return_value = (
            "Transformers are a type of neural network architecture.",
            ["NLP Course - Lesson 2"],
        )
        mock_rag_system.session_manager.create_session.return_value = "session_1"

        response = test_client.post("/api/query", json={"query": "What are transformers?"})

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Transformers are a type of neural network architecture."
        assert data["sources"] == ["NLP Course - Lesson 2"]
        assert data["session_id"] == "session_1"

    def test_new_session_created_when_none_provided(self, test_client, mock_rag_system):
        """session_manager.create_session is called when session_id is omitted."""
        mock_rag_system.session_manager.create_session.return_value = "session_new"
        mock_rag_system.query.return_value = ("Some answer.", [])

        response = test_client.post("/api/query", json={"query": "Hello?"})

        assert response.status_code == 200
        mock_rag_system.session_manager.create_session.assert_called_once()
        assert response.json()["session_id"] == "session_new"

    def test_existing_session_id_is_forwarded_to_rag(self, test_client, mock_rag_system):
        """Provided session_id is passed to RAGSystem.query and echoed back."""
        mock_rag_system.query.return_value = ("Follow-up reply.", [])

        response = test_client.post(
            "/api/query",
            json={"query": "Follow-up question", "session_id": "session_existing"},
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "session_existing"
        mock_rag_system.session_manager.create_session.assert_not_called()
        mock_rag_system.query.assert_called_once_with("Follow-up question", "session_existing")

    def test_missing_query_field_returns_422(self, test_client):
        """Request body without the required 'query' field is rejected."""
        response = test_client.post("/api/query", json={"session_id": "s1"})
        assert response.status_code == 422

    def test_empty_query_string_is_accepted(self, test_client, mock_rag_system):
        """An empty query string passes schema validation (logic is downstream)."""
        mock_rag_system.query.return_value = ("I need more context to answer.", [])
        mock_rag_system.session_manager.create_session.return_value = "session_1"

        response = test_client.post("/api/query", json={"query": ""})

        assert response.status_code == 200

    def test_rag_exception_returns_500_with_detail(self, test_client, mock_rag_system):
        """If RAGSystem.query raises, the endpoint returns 500 with the error message."""
        mock_rag_system.query.side_effect = RuntimeError("ChromaDB connection failed")
        mock_rag_system.session_manager.create_session.return_value = "session_1"

        response = test_client.post("/api/query", json={"query": "What is ML?"})

        assert response.status_code == 500
        assert "ChromaDB connection failed" in response.json()["detail"]

    def test_empty_sources_list_returned(self, test_client, mock_rag_system):
        """Response includes an empty sources list when no content was retrieved."""
        mock_rag_system.query.return_value = ("General knowledge answer.", [])
        mock_rag_system.session_manager.create_session.return_value = "session_1"

        response = test_client.post("/api/query", json={"query": "Tell me something general."})

        assert response.status_code == 200
        assert response.json()["sources"] == []

    def test_multiple_sources_returned(self, test_client, mock_rag_system):
        """All source strings from multiple chunks are present in the response."""
        sources = ["Course A - Lesson 1", "Course B - Lesson 3", "Course A - Lesson 4"]
        mock_rag_system.query.return_value = ("Comprehensive answer.", sources)
        mock_rag_system.session_manager.create_session.return_value = "session_1"

        response = test_client.post("/api/query", json={"query": "Compare the courses."})

        assert response.status_code == 200
        assert response.json()["sources"] == sources

    def test_request_body_must_be_json(self, test_client):
        """Non-JSON body returns 422."""
        response = test_client.post(
            "/api/query",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:

    def test_returns_total_courses_and_titles(self, test_client, mock_rag_system):
        """Default mock returns correct count and title list."""
        response = test_client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 2
        assert data["course_titles"] == ["Course A", "Course B"]

    def test_empty_catalog_returns_zero_count(self, test_client, mock_rag_system):
        """When no courses are loaded both count and list are empty."""
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }

        response = test_client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_total_courses_matches_titles_length(self, test_client, mock_rag_system):
        """total_courses is consistent with the length of course_titles."""
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["Alpha", "Beta", "Gamma"],
        }

        response = test_client.get("/api/courses")
        data = response.json()

        assert data["total_courses"] == len(data["course_titles"])

    def test_analytics_exception_returns_500(self, test_client, mock_rag_system):
        """If get_course_analytics raises, the endpoint returns 500."""
        mock_rag_system.get_course_analytics.side_effect = Exception("DB unavailable")

        response = test_client.get("/api/courses")

        assert response.status_code == 500
        assert "DB unavailable" in response.json()["detail"]

    def test_courses_endpoint_does_not_require_body(self, test_client):
        """GET /api/courses succeeds with no request body (it is a GET)."""
        response = test_client.get("/api/courses")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestRootEndpoint:

    def test_root_returns_200(self, test_client):
        """Root endpoint is reachable and returns HTTP 200."""
        response = test_client.get("/")
        assert response.status_code == 200

    def test_root_returns_json(self, test_client):
        """Root endpoint responds with a JSON content type."""
        response = test_client.get("/")
        assert "application/json" in response.headers["content-type"]

    def test_root_response_has_status_field(self, test_client):
        """Root response body contains the expected status field."""
        response = test_client.get("/")
        assert response.json().get("status") == "ok"
