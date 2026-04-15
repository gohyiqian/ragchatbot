"""
Tests for AIGenerator.generate_response() and _handle_tool_execution()

Covers:
  - Direct text response (no tool use)
  - Tool use is triggered for course-specific questions
  - Tool result is correctly packaged and sent back to Claude
  - Second API call excludes tools (prevents infinite tool-call loop)
  - Final text is extracted from the response
"""
import pytest
from unittest.mock import MagicMock, patch, call

from ai_generator import AIGenerator


# ──────────────────────── helpers ────────────────────────────────────────────

def _text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(name: str, input_data: dict, tool_id: str = "toolu_test01"):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _response(stop_reason: str, content_blocks: list):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content_blocks
    return resp


# ──────────────────────── fixtures ───────────────────────────────────────────

@pytest.fixture
def generator():
    """AIGenerator with a mocked Anthropic client (no real API calls)."""
    with patch("ai_generator.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        gen = AIGenerator(api_key="test-key", model="claude-test")
    # Expose the mock so tests can configure it
    gen._mock_client = mock_client
    return gen


# ──────────────────────── direct response (no tools) ─────────────────────────

class TestDirectResponse:

    def test_returns_text_from_response(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("Paris is the capital of France.")]
        )
        result = generator.generate_response("What is the capital of France?")
        assert result == "Paris is the capital of France."

    def test_api_called_exactly_once(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("Answer.")]
        )
        generator.generate_response("General question?")
        assert generator._mock_client.messages.create.call_count == 1

    def test_tool_manager_not_invoked_for_direct_response(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("Answer.")]
        )
        tool_manager = MagicMock()
        generator.generate_response("General question?", tool_manager=tool_manager)
        tool_manager.execute_tool.assert_not_called()

    def test_system_prompt_included_in_call(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("ok")]
        )
        generator.generate_response("hi")
        call_kwargs = generator._mock_client.messages.create.call_args[1]
        assert "system" in call_kwargs
        assert len(call_kwargs["system"]) > 0

    def test_conversation_history_appended_to_system(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("ok")]
        )
        generator.generate_response("hi", conversation_history="User: hello\nAssistant: hi")
        call_kwargs = generator._mock_client.messages.create.call_args[1]
        assert "Previous conversation" in call_kwargs["system"]
        assert "User: hello" in call_kwargs["system"]

    def test_tools_included_when_provided(self, generator):
        generator._mock_client.messages.create.return_value = _response(
            "end_turn", [_text_block("ok")]
        )
        tools = [{"name": "search_course_content"}]
        generator.generate_response("hi", tools=tools)
        call_kwargs = generator._mock_client.messages.create.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == {"type": "auto"}


# ──────────────────────── tool-use flow ──────────────────────────────────────

class TestToolUseFlow:

    def test_tool_manager_execute_called_with_correct_args(self, generator):
        tool_block = _tool_use_block(
            "search_course_content", {"query": "What is MCP?"}
        )
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("MCP is Model Context Protocol.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "search result"

        generator.generate_response(
            "What is MCP?",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="What is MCP?"
        )

    def test_api_called_twice_for_tool_use(self, generator):
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("Answer.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert generator._mock_client.messages.create.call_count == 2

    def test_final_text_is_returned(self, generator):
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("Final answer from Claude.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        result = generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        assert result == "Final answer from Claude."

    def test_tool_result_sent_in_second_api_call(self, generator):
        tool_block = _tool_use_block(
            "search_course_content", {"query": "test"}, tool_id="toolu_abc123"
        )
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("Done.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "the search result"

        generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = generator._mock_client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]

        # Find the user message that contains the tool result
        tool_result_message = next(
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        )
        tool_result = tool_result_message["content"][0]

        assert tool_result["type"] == "tool_result"
        assert tool_result["tool_use_id"] == "toolu_abc123"
        assert tool_result["content"] == "the search result"

    def test_second_api_call_excludes_tools(self, generator):
        """
        The final API call must NOT include tools to prevent an infinite tool-use loop.
        """
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("Done.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = generator._mock_client.messages.create.call_args_list[1][1]
        assert "tools" not in second_call_kwargs, (
            "The final API call should not include tools — it would trigger "
            "another tool-use loop."
        )

    def test_assistant_tool_use_message_included_in_second_call(self, generator):
        """
        The assistant's tool-use response must be part of the message history
        sent in the second API call (required by the Anthropic API).
        """
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        first_response = _response("tool_use", [tool_block])
        generator._mock_client.messages.create.side_effect = [
            first_response,
            _response("end_turn", [_text_block("Done.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = generator._mock_client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        # Should contain: original user, assistant tool-use, user tool-result
        assert len(messages) >= 3
        assistant_msg = next(m for m in messages if m["role"] == "assistant")
        assert assistant_msg["content"] is first_response.content


# ──────────── tool returns error string (MAX_RESULTS=0 scenario) ─────────────

class TestToolErrorScenario:
    """
    When the search tool returns an error string (e.g. because MAX_RESULTS=0),
    the AIGenerator should still complete without raising an exception —
    it sends the error string as the tool result and gets a final response.
    """

    def test_error_tool_result_does_not_raise(self, generator):
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response(
                "end_turn",
                [_text_block("I could not find relevant course content.")],
            ),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = (
            "Search error: Number of requested results 0 cannot be negative, or zero."
        )

        # Should NOT raise; should return Claude's degraded response
        result = generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )
        assert "could not find" in result.lower()

    def test_error_tool_result_is_passed_verbatim_to_claude(self, generator):
        error_msg = "Search error: n_results=0 is invalid."
        tool_block = _tool_use_block("search_course_content", {"query": "test"})
        generator._mock_client.messages.create.side_effect = [
            _response("tool_use", [tool_block]),
            _response("end_turn", [_text_block("No results.")]),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = error_msg

        generator.generate_response(
            "course question",
            tools=[{"name": "search_course_content"}],
            tool_manager=tool_manager,
        )

        second_call_kwargs = generator._mock_client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        tool_result_msg = next(
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        )
        assert tool_result_msg["content"][0]["content"] == error_msg
