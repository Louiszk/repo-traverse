from unittest.mock import MagicMock

from app.agent import AgentState, call_tools
from app.config import settings
from app.utils import get_token_count
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig


def test_get_token_count_string():
    text = "Hello world, this is a test prompt for tiktoken counting."
    count = get_token_count(text)
    assert isinstance(count, int)
    assert count > 0


def test_get_token_count_messages():
    messages = [
        HumanMessage(content="What is the architecture?"),
        AIMessage(
            content="Let me check the code.",
            tool_calls=[{"id": "call_123", "name": "search_code", "args": {"query": "main"}}],
        ),
        ToolMessage(content="Found main function", tool_call_id="call_123", name="search_code"),
    ]
    count = get_token_count(messages)
    assert isinstance(count, int)
    assert count > 20


def test_call_tools_individual_truncation(monkeypatch):
    monkeypatch.setattr(settings, "max_context_tokens", 100)
    # individual tool limit will be 100 // 4 = 25 tokens

    long_output = "data " * 200
    mock_execute = MagicMock(return_value=[ToolMessage(content=long_output, tool_call_id="c1", name="search_code")])
    monkeypatch.setattr("app.agent.execute_tool_calls", mock_execute)

    state: AgentState = {
        "messages": [
            HumanMessage(content="hi"),
            AIMessage(content="call", tool_calls=[{"id": "c1", "name": "search", "args": {}}]),
        ]
    }
    result = call_tools(state, RunnableConfig())
    tool_msgs = result["messages"]

    assert len(tool_msgs) == 1
    # Check that individual truncation appended notice
    assert "[Output truncated]" in str(tool_msgs[0].content) or "Context window limit reached" in str(
        tool_msgs[0].content
    )


def test_call_tools_total_context_limit_discard(monkeypatch):
    monkeypatch.setattr(settings, "max_context_tokens", 100)
    monkeypatch.setattr(settings, "max_completion_tokens", 20)

    # Safe limit = 100 - 20 - 2000 = -1920 (will immediately trigger discard if total_tokens > safe_limit)
    mock_execute = MagicMock(
        return_value=[ToolMessage(content="some tool output", tool_call_id="c1", name="search_code")]
    )
    monkeypatch.setattr("app.agent.execute_tool_calls", mock_execute)

    state: AgentState = {"messages": [HumanMessage(content="Hello world!")]}
    result = call_tools(state, RunnableConfig())
    tool_msgs = result["messages"]

    assert len(tool_msgs) == 1
    assert "Tool output discarded. Context window limit reached" in str(tool_msgs[0].content)
    assert getattr(tool_msgs[0], "status", None) == "error"
