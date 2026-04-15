"""
Tests for RAGSystem.query() — the top-level content-query pipeline.

Covers:
  - query() passes tools and tool_manager to AIGenerator
  - query() returns (answer, sources) tuple
  - query() updates session conversation history
  - BUG: config.MAX_RESULTS=0 prevents any content from being retrieved
  - Integration: when the AI triggers tool use, the real VectorStore is searched
"""
import pytest
from unittest.mock import MagicMock, patch

from vector_store import SearchResults
from config import config


# ──────────────────────── helpers ────────────────────────────────────────────

def _text_block(text: str):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(name: str, input_data: dict, tool_id: str = "toolu_test"):
    b = MagicMock()
    b.type = "tool_use"
    b.id = tool_id
    b.name = name
    b.input = input_data
    return b


def _response(stop_reason: str, content_blocks: list):
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = content_blocks
    return r


# ──────────────────── BUG: MAX_RESULTS = 0 in config ─────────────────────────

class TestConfigBug:
    """
    BUG: config.MAX_RESULTS is set to 0 instead of a positive integer.

    Impact chain:
        config.MAX_RESULTS = 0
        → VectorStore(max_results=0)
        → VectorStore.search() passes n_results=0 to ChromaDB
        → ChromaDB raises ValueError
        → SearchResults.empty(error_msg) returned
        → CourseSearchTool.execute() returns the error string
        → Claude receives an error as the tool result
        → Claude cannot answer content questions

    Fix: set MAX_RESULTS = 5 in backend/config.py
    """

    def test_max_results_is_positive(self):
        assert config.MAX_RESULTS > 0, (
            f"\n\nBUG DETECTED — config.MAX_RESULTS = {config.MAX_RESULTS}\n"
            "Must be a positive integer (e.g. 5).\n"
            "With 0, ChromaDB raises ValueError on every content search.\n"
            "Fix: change MAX_RESULTS in backend/config.py from 0 to 5."
        )


# ─────────────── VectorStore behaviour with zero max_results ─────────────────

class TestVectorStoreZeroMaxResults:

    def test_search_with_zero_n_results_returns_error(self):
        """
        Reproduce the runtime failure: max_results=0 causes every search to
        return SearchResults.empty(error_msg) instead of real documents.
        """
        from unittest.mock import patch, MagicMock
        from vector_store import VectorStore

        with patch("vector_store.chromadb.PersistentClient") as mock_cls, \
             patch("vector_store.chromadb.utils.embedding_functions"
                   ".SentenceTransformerEmbeddingFunction"):

            coll = MagicMock()
            coll.query.side_effect = ValueError(
                "Number of requested results 0 cannot be negative, or zero."
            )
            client = MagicMock()
            client.get_or_create_collection.return_value = coll
            mock_cls.return_value = client

            store = VectorStore("./test", "model", max_results=0)
            results = store.search("What is MCP?")

        assert results.error is not None, "Expected error — got success with n_results=0"
        assert "Search error" in results.error
        assert results.is_empty()

    def test_search_with_positive_n_results_succeeds(self):
        """Contrast: max_results=5 returns documents correctly."""
        from unittest.mock import patch, MagicMock
        from vector_store import VectorStore

        with patch("vector_store.chromadb.PersistentClient") as mock_cls, \
             patch("vector_store.chromadb.utils.embedding_functions"
                   ".SentenceTransformerEmbeddingFunction"):

            coll = MagicMock()
            coll.query.return_value = {
                "documents": [["MCP enables tool use by AI models."]],
                "metadatas": [[{"course_title": "MCP", "lesson_number": 1}]],
                "distances": [[0.1]],
            }
            client = MagicMock()
            client.get_or_create_collection.return_value = coll
            mock_cls.return_value = client

            store = VectorStore("./test", "model", max_results=5)
            results = store.search("What is MCP?")

        assert results.error is None
        assert not results.is_empty()
        assert "MCP enables" in results.documents[0]


# ──────────────────────── RAGSystem.query() ──────────────────────────────────

@pytest.fixture
def rag_system():
    """RAGSystem with all external I/O mocked (no Anthropic calls, no ChromaDB)."""
    with patch("rag_system.VectorStore") as mock_vs_cls, \
         patch("rag_system.AIGenerator") as mock_gen_cls, \
         patch("rag_system.DocumentProcessor"):

        mock_store = MagicMock()
        mock_store.search.return_value = SearchResults(
            documents=["MCP is a protocol for AI tool use."],
            metadata=[{"course_title": "Intro to MCP", "lesson_number": 1}],
            distances=[0.1],
        )
        mock_store.get_lesson_link.return_value = None
        mock_vs_cls.return_value = mock_store

        mock_gen = MagicMock()
        mock_gen.generate_response.return_value = "MCP stands for Model Context Protocol."
        mock_gen_cls.return_value = mock_gen

        from rag_system import RAGSystem
        system = RAGSystem(config)

    yield system, mock_store, mock_gen


class TestRAGSystemQuery:

    def test_query_returns_answer_string(self, rag_system):
        system, _, mock_gen = rag_system
        mock_gen.generate_response.return_value = "MCP stands for Model Context Protocol."
        answer, _ = system.query("What is MCP?")
        assert answer == "MCP stands for Model Context Protocol."

    def test_query_returns_list_as_sources(self, rag_system):
        system, _, _ = rag_system
        _, sources = system.query("What is MCP?")
        assert isinstance(sources, list)

    def test_query_passes_tools_to_generator(self, rag_system):
        system, _, mock_gen = rag_system
        system.query("What is MCP?")
        call_kwargs = mock_gen.generate_response.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) > 0

    def test_query_passes_tool_manager_to_generator(self, rag_system):
        system, _, mock_gen = rag_system
        system.query("What is MCP?")
        call_kwargs = mock_gen.generate_response.call_args[1]
        assert "tool_manager" in call_kwargs
        assert call_kwargs["tool_manager"] is system.tool_manager

    def test_query_passes_conversation_history_to_generator(self, rag_system):
        system, _, mock_gen = rag_system
        session_id = system.session_manager.create_session()
        system.session_manager.add_exchange(session_id, "hello", "hi")

        system.query("follow-up question", session_id)

        call_kwargs = mock_gen.generate_response.call_args[1]
        history = call_kwargs.get("conversation_history")
        assert history is not None
        assert "hello" in history

    def test_query_updates_session_history(self, rag_system):
        system, _, mock_gen = rag_system
        mock_gen.generate_response.return_value = "The answer."
        session_id = system.session_manager.create_session()

        system.query("What is MCP?", session_id)

        history = system.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "What is MCP?" in history
        assert "The answer." in history

    def test_sources_reset_after_query(self, rag_system):
        system, _, _ = rag_system
        # Seed some stale sources
        system.tool_manager.tools["search_course_content"].last_sources = [
            {"name": "Old source", "link": None}
        ]
        system.query("What is MCP?")
        # After the query, sources should be reset (consumed once, then cleared)
        assert system.tool_manager.tools["search_course_content"].last_sources == []


# ──────────── Integration: tool-use triggers real VectorStore.search ──────────

class TestRAGSystemToolIntegration:
    """
    Patch only the Anthropic client; let the real CourseSearchTool and a mocked
    VectorStore run so we can verify the full search path is exercised.
    """

    def test_vector_store_searched_when_claude_calls_tool(self):
        with patch("rag_system.VectorStore") as mock_vs_cls, \
             patch("rag_system.DocumentProcessor"), \
             patch("ai_generator.anthropic.Anthropic") as mock_anthropic_cls:

            # Vector store returns one document
            mock_store = MagicMock()
            mock_store.search.return_value = SearchResults(
                documents=["MCP enables AI models to use tools safely."],
                metadata=[{"course_title": "Intro to MCP", "lesson_number": 1}],
                distances=[0.1],
            )
            mock_store.get_lesson_link.return_value = None
            mock_vs_cls.return_value = mock_store

            # Anthropic: first call triggers tool use, second returns final answer
            tool_block = _tool_use_block(
                "search_course_content", {"query": "What is MCP?"}, "toolu_001"
            )
            mock_messages = MagicMock()
            mock_messages.create.side_effect = [
                _response("tool_use", [tool_block]),
                _response("end_turn", [_text_block("MCP is Model Context Protocol.")]),
            ]
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_anthropic_cls.return_value = mock_client

            from rag_system import RAGSystem
            system = RAGSystem(config)
            answer, sources = system.query("What is MCP?")

        assert answer == "MCP is Model Context Protocol."
        mock_store.search.assert_called_once_with(
            query="What is MCP?", course_name=None, lesson_number=None
        )

    def test_search_tool_sources_returned_after_tool_use(self):
        with patch("rag_system.VectorStore") as mock_vs_cls, \
             patch("rag_system.DocumentProcessor"), \
             patch("ai_generator.anthropic.Anthropic") as mock_anthropic_cls:

            mock_store = MagicMock()
            mock_store.search.return_value = SearchResults(
                documents=["Content here."],
                metadata=[{"course_title": "Intro to MCP", "lesson_number": 2}],
                distances=[0.2],
            )
            mock_store.get_lesson_link.return_value = "https://example.com/lesson/2"
            mock_vs_cls.return_value = mock_store

            tool_block = _tool_use_block(
                "search_course_content", {"query": "lesson content"}, "toolu_002"
            )
            mock_messages = MagicMock()
            mock_messages.create.side_effect = [
                _response("tool_use", [tool_block]),
                _response("end_turn", [_text_block("Here is what I found.")]),
            ]
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_anthropic_cls.return_value = mock_client

            from rag_system import RAGSystem
            system = RAGSystem(config)
            answer, sources = system.query("Tell me about lesson content")

        assert len(sources) == 1
        assert sources[0]["name"] == "Intro to MCP - Lesson 2"
        assert sources[0]["link"] == "https://example.com/lesson/2"

    def test_no_content_returned_when_max_results_is_zero(self):
        """
        When config.MAX_RESULTS=0, the search tool receives an error string
        and Claude cannot answer with real course content.

        This test is EXPECTED TO FAIL until config.MAX_RESULTS is set to > 0.
        It demonstrates the downstream effect of the bug.
        """
        with patch("rag_system.VectorStore") as mock_vs_cls, \
             patch("rag_system.DocumentProcessor"), \
             patch("ai_generator.anthropic.Anthropic") as mock_anthropic_cls:

            # Simulate what happens when n_results=0 reaches ChromaDB
            mock_store = MagicMock()
            mock_store.search.return_value = SearchResults.empty(
                "Search error: Number of requested results 0 cannot be negative, or zero."
            )
            mock_vs_cls.return_value = mock_store

            tool_block = _tool_use_block(
                "search_course_content", {"query": "What is MCP?"}, "toolu_003"
            )
            mock_messages = MagicMock()
            mock_messages.create.side_effect = [
                _response("tool_use", [tool_block]),
                _response(
                    "end_turn",
                    [_text_block("I was unable to find relevant course content.")],
                ),
            ]
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_anthropic_cls.return_value = mock_client

            from rag_system import RAGSystem
            system = RAGSystem(config)
            answer, sources = system.query("What is MCP?")

        # Sources must be empty — no content was retrieved
        assert sources == [], (
            "Expected empty sources when search fails due to MAX_RESULTS=0"
        )
        # The answer reflects the search failure
        assert "unable" in answer.lower() or "not find" in answer.lower() or \
               "could not" in answer.lower(), (
            f"Expected a 'not found' response but got: {answer!r}\n"
            "This is the degraded output caused by MAX_RESULTS=0."
        )
