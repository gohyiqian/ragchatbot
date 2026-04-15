"""
Tests for CourseSearchTool.execute()

Covers:
  - Happy-path formatting
  - Error propagation when the vector store returns an error
  - Empty-result messages (with and without filters)
  - Filter arguments are forwarded to the vector store
  - Sources (last_sources) are tracked correctly
  - BUG: MAX_RESULTS=0 in config causes every search to fail
"""
import pytest
from unittest.mock import MagicMock, call

from vector_store import SearchResults
from search_tools import CourseSearchTool, ToolManager


# ──────────────────────────── fixtures ───────────────────────────────────────

@pytest.fixture
def sample_results():
    return SearchResults(
        documents=[
            "MCP enables tools to be used by AI models.",
            "Agents can chain multiple tool calls together.",
        ],
        metadata=[
            {"course_title": "Intro to MCP", "lesson_number": 1},
            {"course_title": "Intro to MCP", "lesson_number": 2},
        ],
        distances=[0.1, 0.2],
    )


@pytest.fixture
def empty_results():
    return SearchResults(documents=[], metadata=[], distances=[])


@pytest.fixture
def error_results():
    return SearchResults.empty(
        "Search error: Number of requested results 0 cannot be negative, or zero."
    )


@pytest.fixture
def mock_store(sample_results):
    store = MagicMock()
    store.search.return_value = sample_results
    store.get_lesson_link.return_value = "https://example.com/lesson/1"
    return store


@pytest.fixture
def tool(mock_store):
    return CourseSearchTool(mock_store)


# ──────────────────────── happy-path formatting ───────────────────────────────

class TestCourseSearchToolExecuteFormats:

    def test_result_contains_course_title(self, tool):
        result = tool.execute("What is MCP?")
        assert "Intro to MCP" in result

    def test_result_contains_lesson_number(self, tool):
        result = tool.execute("What is MCP?")
        assert "Lesson 1" in result
        assert "Lesson 2" in result

    def test_result_contains_document_text(self, tool):
        result = tool.execute("What is MCP?")
        assert "MCP enables tools to be used by AI models." in result
        assert "Agents can chain multiple tool calls together." in result

    def test_multiple_results_separated_by_blank_line(self, tool):
        result = tool.execute("What is MCP?")
        # Results joined with "\n\n"
        assert "\n\n" in result


# ──────────────────────── error / empty handling ─────────────────────────────

class TestCourseSearchToolExecuteErrors:

    def test_returns_error_string_when_store_errors(self, tool, mock_store, error_results):
        mock_store.search.return_value = error_results
        result = tool.execute("What is MCP?")
        assert "Search error" in result

    def test_returns_error_string_verbatim(self, tool, mock_store):
        mock_store.search.return_value = SearchResults.empty("Search error: boom")
        result = tool.execute("query")
        assert result == "Search error: boom"

    def test_returns_no_results_message_on_empty(self, tool, mock_store, empty_results):
        mock_store.search.return_value = empty_results
        result = tool.execute("unknown topic")
        assert "No relevant content found" in result

    def test_no_results_message_includes_course_filter(self, tool, mock_store, empty_results):
        mock_store.search.return_value = empty_results
        result = tool.execute("unknown topic", course_name="Advanced MCP")
        assert "No relevant content found" in result
        assert "Advanced MCP" in result

    def test_no_results_message_includes_lesson_filter(self, tool, mock_store, empty_results):
        mock_store.search.return_value = empty_results
        result = tool.execute("unknown topic", lesson_number=3)
        assert "No relevant content found" in result
        assert "3" in result


# ──────────────────────── argument forwarding ────────────────────────────────

class TestCourseSearchToolExecuteArguments:

    def test_passes_query_to_store(self, tool, mock_store):
        tool.execute("What is MCP?")
        mock_store.search.assert_called_once_with(
            query="What is MCP?", course_name=None, lesson_number=None
        )

    def test_passes_course_name_to_store(self, tool, mock_store):
        tool.execute("concepts", course_name="Intro to MCP")
        mock_store.search.assert_called_once_with(
            query="concepts", course_name="Intro to MCP", lesson_number=None
        )

    def test_passes_lesson_number_to_store(self, tool, mock_store):
        tool.execute("concepts", lesson_number=2)
        mock_store.search.assert_called_once_with(
            query="concepts", course_name=None, lesson_number=2
        )

    def test_passes_all_filters_to_store(self, tool, mock_store):
        tool.execute("concepts", course_name="MCP", lesson_number=1)
        mock_store.search.assert_called_once_with(
            query="concepts", course_name="MCP", lesson_number=1
        )


# ──────────────────────── sources tracking ───────────────────────────────────

class TestCourseSearchToolSources:

    def test_last_sources_populated_after_execute(self, tool):
        tool.execute("What is MCP?")
        assert len(tool.last_sources) == 2

    def test_last_sources_have_name_and_link_keys(self, tool):
        tool.execute("What is MCP?")
        for source in tool.last_sources:
            assert "name" in source
            assert "link" in source

    def test_last_sources_name_includes_lesson_number(self, tool):
        tool.execute("What is MCP?")
        assert tool.last_sources[0]["name"] == "Intro to MCP - Lesson 1"
        assert tool.last_sources[1]["name"] == "Intro to MCP - Lesson 2"

    def test_last_sources_link_comes_from_store(self, tool, mock_store):
        mock_store.get_lesson_link.return_value = "https://example.com/lesson/1"
        tool.execute("What is MCP?")
        assert tool.last_sources[0]["link"] == "https://example.com/lesson/1"

    def test_last_sources_empty_on_error_result(self, tool, mock_store, error_results):
        mock_store.search.return_value = error_results
        tool.execute("What is MCP?")
        # execute() returns early with the error string; sources never set
        assert tool.last_sources == []

    def test_last_sources_empty_on_empty_results(self, tool, mock_store, empty_results):
        mock_store.search.return_value = empty_results
        tool.execute("What is MCP?")
        assert tool.last_sources == []


# ──────────────────────── BUG: MAX_RESULTS = 0 ───────────────────────────────

class TestMaxResultsZeroBug:
    """
    BUG: config.MAX_RESULTS is set to 0 instead of a positive integer.

    VectorStore is initialised with max_results=0.  When search() is called,
    it computes search_limit=0 and passes n_results=0 to ChromaDB, which raises:
        ValueError: Number of requested results 0 cannot be negative, or zero.
    That exception is caught and returned as SearchResults.empty(error_msg).
    CourseSearchTool.execute() then returns the error string as the tool result,
    so Claude never receives real content and content queries degrade silently.

    Fix: set MAX_RESULTS = 5 in backend/config.py.
    """

    def test_config_max_results_is_positive(self):
        from config import config
        assert config.MAX_RESULTS > 0, (
            f"BUG DETECTED — config.MAX_RESULTS = {config.MAX_RESULTS}.\n"
            "Must be a positive integer (e.g. 5).\n"
            "With 0, ChromaDB raises ValueError on every content search and "
            "CourseSearchTool.execute() returns an error string instead of results."
        )

    def test_vector_store_search_with_zero_n_results_returns_error(self):
        """
        VectorStore.search() with max_results=0 returns an error SearchResults,
        mirroring what happens at runtime when config.MAX_RESULTS=0.
        """
        from unittest.mock import patch, MagicMock
        from vector_store import VectorStore

        with patch("vector_store.chromadb.PersistentClient") as mock_client_cls, \
             patch("vector_store.chromadb.utils.embedding_functions"
                   ".SentenceTransformerEmbeddingFunction"):

            mock_collection = MagicMock()
            mock_collection.query.side_effect = ValueError(
                "Number of requested results 0 cannot be negative, or zero."
            )
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_client_cls.return_value = mock_client

            store = VectorStore("./test_chroma", "all-MiniLM-L6-v2", max_results=0)
            results = store.search("What is MCP?")

        assert results.error is not None, (
            "Expected SearchResults with an error when n_results=0, got success."
        )
        assert "Search error" in results.error
        assert results.is_empty()

    def test_vector_store_search_with_positive_n_results_succeeds(self):
        """Contrast: max_results=5 works correctly."""
        from unittest.mock import patch, MagicMock
        from vector_store import VectorStore

        with patch("vector_store.chromadb.PersistentClient") as mock_client_cls, \
             patch("vector_store.chromadb.utils.embedding_functions"
                   ".SentenceTransformerEmbeddingFunction"):

            mock_collection = MagicMock()
            mock_collection.query.return_value = {
                "documents": [["MCP content here"]],
                "metadatas": [[{"course_title": "MCP", "lesson_number": 1}]],
                "distances": [[0.1]],
            }
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_client_cls.return_value = mock_client

            store = VectorStore("./test_chroma", "all-MiniLM-L6-v2", max_results=5)
            results = store.search("What is MCP?")

        assert results.error is None
        assert not results.is_empty()
        assert results.documents[0] == "MCP content here"

    def test_execute_returns_error_when_store_has_zero_max_results(self):
        """
        End-to-end: CourseSearchTool.execute() returns an error string
        (instead of formatted content) when max_results=0 causes the search to fail.
        """
        from unittest.mock import patch, MagicMock
        from vector_store import VectorStore

        with patch("vector_store.chromadb.PersistentClient") as mock_client_cls, \
             patch("vector_store.chromadb.utils.embedding_functions"
                   ".SentenceTransformerEmbeddingFunction"):

            mock_collection = MagicMock()
            mock_collection.query.side_effect = ValueError(
                "Number of requested results 0 cannot be negative, or zero."
            )
            mock_client = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_client_cls.return_value = mock_client

            buggy_store = VectorStore("./test_chroma", "all-MiniLM-L6-v2", max_results=0)
            buggy_tool = CourseSearchTool(buggy_store)
            result = buggy_tool.execute("What is MCP?")

        # The tool should return an error string, not formatted course content
        assert "Search error" in result, (
            f"Expected search error due to n_results=0, but got: {result!r}"
        )
