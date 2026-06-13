from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from src.agent.history import sanitize_messages_for_storage

BIG = "x" * 5000


def _sample_messages() -> list:
    """A realistic two-message run: assistant text + tool call, then the tool result."""
    return [
        ModelResponse(
            parts=[
                TextPart(content="Let me search GitHub."),
                ToolCallPart(tool_name="search_issues", args={"q": "asyncio"}, tool_call_id="call-1"),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="search_issues", content=BIG, tool_call_id="call-1"),
                UserPromptPart(content="what did you find?"),
            ]
        ),
    ]


def test_large_tool_result_truncated_pairing_and_text_preserved() -> None:
    messages = _sample_messages()
    out = sanitize_messages_for_storage(messages, max_chars=600)

    # Assistant text + tool call preserved verbatim.
    response = out[0]
    assert isinstance(response, ModelResponse)
    assert isinstance(response.parts[0], TextPart)
    assert response.parts[0].content == "Let me search GitHub."
    call = response.parts[1]
    assert isinstance(call, ToolCallPart)
    assert call.tool_call_id == "call-1"

    request = out[1]
    assert isinstance(request, ModelRequest)
    tool_return = request.parts[0]
    assert isinstance(tool_return, ToolReturnPart)
    # Content truncated with placeholder, but tool_name/tool_call_id intact for replay pairing.
    assert tool_return.tool_name == "search_issues"
    assert tool_return.tool_call_id == "call-1"
    assert len(str(tool_return.content)) < len(BIG)
    assert "[tool result truncated from history: 5000 chars]" in str(tool_return.content)
    assert str(tool_return.content).startswith("x" * 600)

    # Surrounding user prompt preserved verbatim.
    user_part = request.parts[1]
    assert isinstance(user_part, UserPromptPart)
    assert user_part.content == "what did you find?"


def test_small_tool_result_passes_through_unchanged() -> None:
    small = ToolReturnPart(tool_name="t", content="tiny result", tool_call_id="c")
    messages = [ModelRequest(parts=[small])]
    out = sanitize_messages_for_storage(messages, max_chars=600)
    result_part = out[0].parts[0]
    assert isinstance(result_part, ToolReturnPart)
    assert result_part.content == "tiny result"


def test_max_chars_zero_strips_to_placeholder_only() -> None:
    messages = [ModelRequest(parts=[ToolReturnPart(tool_name="t", content="abc", tool_call_id="c")])]
    out = sanitize_messages_for_storage(messages, max_chars=0)
    result_part = out[0].parts[0]
    assert isinstance(result_part, ToolReturnPart)
    assert result_part.content == "[tool result truncated from history: 3 chars]"


def test_large_retry_prompt_truncated() -> None:
    messages = [ModelRequest(parts=[RetryPromptPart(content=BIG, tool_name="t", tool_call_id="c")])]
    out = sanitize_messages_for_storage(messages, max_chars=600)
    part = out[0].parts[0]
    assert isinstance(part, RetryPromptPart)
    assert "[tool result truncated from history: 5000 chars]" in str(part.content)
    assert part.tool_call_id == "c"


def test_structured_tool_result_replaced() -> None:
    structured = {"body": BIG, "title": "big issue"}
    messages = [ModelRequest(parts=[ToolReturnPart(tool_name="t", content=structured, tool_call_id="c")])]
    out = sanitize_messages_for_storage(messages, max_chars=600)
    part = out[0].parts[0]
    assert isinstance(part, ToolReturnPart)
    assert "[tool result truncated from history:" in str(part.content)


def test_sanitized_roundtrips_through_type_adapter() -> None:
    """The sanitized list must remain valid message_history shape for replay."""
    out = sanitize_messages_for_storage(_sample_messages(), max_chars=600)
    dumped = ModelMessagesTypeAdapter.dump_json(out)
    reloaded = ModelMessagesTypeAdapter.validate_json(dumped)
    assert len(reloaded) == 2
    request = reloaded[1]
    assert isinstance(request, ModelRequest)
    tool_return = request.parts[0]
    assert isinstance(tool_return, ToolReturnPart)
    # Pairing survives the round-trip.
    assert tool_return.tool_call_id == "call-1"
    assert "[tool result truncated from history:" in str(tool_return.content)
