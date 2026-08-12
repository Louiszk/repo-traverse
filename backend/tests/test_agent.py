import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.agent import AgentState, should_continue
from app.tools import (
    _run_cbm_cli,
    get_architecture,
    get_code_snippet,
    get_saved_schema,
    query_graph,
    search_code,
    search_graph,
    trace_call_path,
)
from app.utils import execute_tool_calls
from langchain_core.runnables import RunnableConfig


def test_run_cbm_cli_missing_session():
    result = _run_cbm_cli(None, "get_architecture", [])
    assert "ERROR: No session_id" in result


def test_run_cbm_cli_missing_dir(tmp_path: Path):
    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        result = _run_cbm_cli("non-existent-session", "get_architecture", [])
        assert "not found" in result


@patch("app.tools.run_isolated_subprocess")
def test_run_cbm_cli_success(mock_subprocess: MagicMock, tmp_path: Path):
    session_dir = tmp_path / "session-test"
    session_dir.mkdir(parents=True)
    (session_dir / "session_meta.json").write_text(
        json.dumps({"session_secret": "secret", "csrf_token": "token", "project_name": "my-test-repo"}),
        encoding="utf-8",
    )

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        mock_tool = MagicMock()
        mock_tool.returncode = 0
        mock_tool.stdout = json.dumps({"architecture": "overview"})

        mock_subprocess.return_value = mock_tool

        res = _run_cbm_cli("session-test", "get_architecture", [])

        assert "architecture" in res
        assert mock_subprocess.call_count == 1
        meta = json.loads((session_dir / "session_meta.json").read_text(encoding="utf-8"))
        assert meta["project_name"] == "my-test-repo"


@patch("app.tools.run_isolated_subprocess")
def test_run_cbm_cli_db_lookup_fallback(mock_subprocess: MagicMock, tmp_path: Path):
    session_dir = tmp_path / "session-test"
    session_dir.mkdir(parents=True)
    (session_dir / "session_meta.json").write_text(
        json.dumps({"session_secret": "secret", "csrf_token": "token"}),
        encoding="utf-8",
    )
    db_path = session_dir / "graph.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE projects (name TEXT PRIMARY KEY, indexed_at TEXT NOT NULL, root_path TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?)",
            ("my-test-repo", "2026-08-01", str(session_dir / "repo")),
        )
        conn.commit()
    finally:
        conn.close()

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        mock_tool = MagicMock()
        mock_tool.returncode = 0
        mock_tool.stdout = json.dumps({"architecture": "overview"})
        mock_subprocess.return_value = mock_tool

        res = _run_cbm_cli("session-test", "get_architecture", [])

        assert "architecture" in res
        assert mock_subprocess.call_count == 1
        meta = json.loads((session_dir / "session_meta.json").read_text(encoding="utf-8"))
        assert meta["project_name"] == "my-test-repo"


@patch("app.tools.run_isolated_subprocess")
def test_run_cbm_cli_missing_project_db(mock_subprocess: MagicMock, tmp_path: Path):
    session_dir = tmp_path / "session-test"
    session_dir.mkdir(parents=True)
    (session_dir / "session_meta.json").write_text(
        json.dumps({"session_secret": "secret", "csrf_token": "token"}),
        encoding="utf-8",
    )

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        res = _run_cbm_cli("session-test", "get_architecture", [])

        assert "No indexed projects" in res
        mock_subprocess.assert_not_called()


@patch("app.tools._run_cbm_cli")
def test_tools_extract_session_id(mock_run_cli: MagicMock):
    config = RunnableConfig(configurable={"session_id": "session-xyz"})

    mock_run_cli.return_value = "ok"

    get_architecture.invoke({}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "get_architecture", [])

    search_graph.invoke({"name_pattern": "main", "label": "Function"}, config=config)
    mock_run_cli.assert_called_with(
        "session-xyz", "search_graph", ["--name-pattern=main", "--label=Function", "--limit=15"]
    )

    search_code.invoke({"pattern": "TODO", "mode": "compact"}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "search_code", ["--pattern=TODO", "--mode=compact", "--limit=10"])

    trace_call_path.invoke({"function_name": "process", "direction": "inbound"}, config=config)
    mock_run_cli.assert_called_with(
        "session-xyz",
        "trace_path",
        ["--function-name=process", "--direction=inbound", "--mode=calls", "--depth=3"],
    )

    get_code_snippet.invoke({"qualified_name": "pkg.mod.func"}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "get_code_snippet", ["--qualified-name=pkg.mod.func"])

    query_graph.invoke({"cypher_query": "MATCH (n) RETURN n LIMIT 5"}, config=config)
    mock_run_cli.assert_called_with(
        "session-xyz", "query_graph", ["--query=MATCH (n) RETURN n LIMIT 5", "--max-rows=100"]
    )


@patch("app.tools._run_cbm_cli")
def test_tools_limit_clamping(mock_run_cli: MagicMock):
    config = RunnableConfig(configurable={"session_id": "session-xyz"})
    mock_run_cli.return_value = "ok"

    # Excessive limit=2000 should be clamped to 50
    search_graph.invoke({"name_pattern": "main", "limit": 2000}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "search_graph", ["--name-pattern=main", "--limit=50"])

    search_code.invoke({"pattern": "TODO", "limit": 2000}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "search_code", ["--pattern=TODO", "--mode=compact", "--limit=50"])

    query_graph.invoke({"cypher_query": "MATCH (n) RETURN n", "max_rows": 5000}, config=config)
    mock_run_cli.assert_called_with("session-xyz", "query_graph", ["--query=MATCH (n) RETURN n", "--max-rows=100"])


def test_get_saved_schema_file(tmp_path: Path):
    session_dir = tmp_path / "session-123"
    session_dir.mkdir(parents=True)
    schema_file = session_dir / "schema.json"
    schema_file.write_text('{"nodes": ["Function"]}')

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        schema = get_saved_schema("session-123")
        assert schema == '{"nodes": ["Function"]}'


def test_get_code_snippet_file_path(tmp_path: Path):
    session_id = "session-test-file"
    repo_dir = tmp_path / session_id / "repo"
    repo_dir.mkdir(parents=True)
    sample_file = repo_dir / "sample.txt"
    sample_file.write_text("line1\nline2\nline3\nline4\nline5", encoding="utf-8")

    config = RunnableConfig(configurable={"session_id": session_id})

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        # Reading lines 2 to 4 of 5
        res = get_code_snippet.invoke({"file_path": "sample.txt", "start_line": 2, "num_lines": 3}, config=config)
        assert "[File: sample.txt | Showing lines 2-4 of 5 total lines]" in res
        assert "line2\nline3\nline4" in res

        # Reading entire small file default (5 lines <= 200 default)
        res_full = get_code_snippet.invoke({"file_path": "sample.txt"}, config=config)
        assert "[File: sample.txt | Showing lines 1-5 of 5 total lines]" in res_full
        assert "line1\nline2\nline3\nline4\nline5" in res_full

        # Non-existent file
        res_missing = get_code_snippet.invoke({"file_path": "missing.txt"}, config=config)
        assert "does not exist" in res_missing

        # Path traversal
        res_traversal = get_code_snippet.invoke({"file_path": "../../../etc/passwd"}, config=config)
        assert "Path traversal attempt detected" in res_traversal

        # Git metadata
        git_dir = repo_dir / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0", encoding="utf-8")
        res_git = get_code_snippet.invoke({"file_path": ".git/config"}, config=config)
        assert "Git metadata is not accessible" in res_git

        # Binary content
        binary_file = repo_dir / "blob.bin"
        binary_file.write_bytes(b"\x00\x01\x02binary-data")
        res_binary = get_code_snippet.invoke({"file_path": "blob.bin"}, config=config)
        assert "Binary or image files are not supported" in res_binary

        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret_data", encoding="utf-8")
        link_file = repo_dir / "link.txt"
        try:
            link_file.symlink_to(outside_file)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this environment")

        res_symlink = get_code_snippet.invoke({"file_path": "link.txt"}, config=config)
        assert "Symlinks are not allowed" in res_symlink


def test_get_code_snippet_max_line_capping(tmp_path: Path):
    session_id = "session-test-cap"
    repo_dir = tmp_path / session_id / "repo"
    repo_dir.mkdir(parents=True)
    big_file = repo_dir / "big.txt"
    big_file.write_text("\n".join(f"line{i}" for i in range(1, 501)), encoding="utf-8")

    config = RunnableConfig(configurable={"session_id": session_id})

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        # Default num_lines (200)
        res_default = get_code_snippet.invoke({"file_path": "big.txt"}, config=config)
        assert "[File: big.txt | Showing lines 1-200 of 500 total lines]" in res_default

        # Exceeding max limit (500 requested -> capped at 400)
        res_capped = get_code_snippet.invoke({"file_path": "big.txt", "num_lines": 500}, config=config)
        assert "[File: big.txt | Showing lines 1-400 of 500 total lines]" in res_capped


def test_get_code_snippet_file_path_oversize_blocked(tmp_path: Path):
    session_id = "session-test-oversize"
    repo_dir = tmp_path / session_id / "repo"
    repo_dir.mkdir(parents=True)
    oversized = repo_dir / "big.txt"
    oversized.write_bytes(b"a" * 1_048_577)

    config = RunnableConfig(configurable={"session_id": session_id})

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        res = get_code_snippet.invoke({"file_path": "big.txt"}, config=config)
        assert "File size exceeds maximum limit" in res


def test_get_code_snippet_file_path_mixed_utf8_replacement(tmp_path: Path):
    session_id = "session-test-mixedutf8"
    repo_dir = tmp_path / session_id / "repo"
    repo_dir.mkdir(parents=True)
    mixed_file = repo_dir / "mixed.txt"
    mixed_file.write_bytes(b"hello\n" + (b"a" * 9000) + b"\xfftail")

    config = RunnableConfig(configurable={"session_id": session_id})

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        res = get_code_snippet.invoke({"file_path": "mixed.txt"}, config=config)
        assert "\ufffd" in res


def test_get_code_snippet_start_line_past_eof_falls_back_to_start(tmp_path: Path):
    session_id = "session-test-start-line"
    repo_dir = tmp_path / session_id / "repo"
    repo_dir.mkdir(parents=True)
    sample_file = repo_dir / "sample.txt"
    sample_file.write_text("line1\nline2\nline3", encoding="utf-8")

    config = RunnableConfig(configurable={"session_id": session_id})

    with patch("app.tools.settings.shared_data_dir", str(tmp_path)):
        res = get_code_snippet.invoke({"file_path": "sample.txt", "start_line": 240, "num_lines": 2}, config=config)
        assert "[File: sample.txt | Showing lines 1-2 of 3 total lines]" in res
        assert "line1\nline2" in res


def test_get_code_snippet_file_path_missing_session():
    config = RunnableConfig(configurable={})
    res = get_code_snippet.invoke({"file_path": "sample.txt"}, config=config)
    assert "ERROR: No session_id" in res


def test_should_continue_router():
    state_empty: AgentState = {"messages": []}
    assert should_continue(state_empty) == "end"

    msg_no_tools = MagicMock()
    msg_no_tools.tool_calls = []
    state_no_tools: AgentState = {"messages": [msg_no_tools]}
    assert should_continue(state_no_tools) == "end"

    msg_with_tools = MagicMock()
    msg_with_tools.tool_calls = [{"name": "get_architecture"}]
    state_with_tools: AgentState = {"messages": [msg_with_tools]}
    assert should_continue(state_with_tools) == "tools"


@patch("app.tools._run_cbm_cli")
def test_execute_tool_calls_custom_utility(mock_run_cli: MagicMock):
    mock_run_cli.return_value = '{"status": "ok"}'
    config = RunnableConfig(configurable={"session_id": "session-123"})

    msg = MagicMock()
    msg.tool_calls = [
        {"id": "call_1", "name": "get_architecture", "args": {}},
        {"id": "call_2", "name": "unknown_tool", "args": {}},
    ]
    msg.invalid_tool_calls = [{"id": "call_3", "name": "bad_tool", "error": "Invalid JSON"}]

    tools = [get_architecture]
    tool_messages = execute_tool_calls(msg, tools, config=config)

    assert len(tool_messages) == 3
    # First is invalid tool call error message
    assert "Invalid JSON" not in tool_messages[0].content
    assert "Failed to parse tool call" in tool_messages[0].content
    assert tool_messages[0].status == "error"

    # Second is valid tool execution
    assert tool_messages[1].tool_call_id == "call_1"
    assert tool_messages[1].name == "get_architecture"

    # Third is unknown tool error
    assert "not a valid tool" in tool_messages[2].content
    assert tool_messages[2].status == "error"


@patch("app.tools._run_cbm_cli")
def test_execute_tool_calls_sanitizes_tool_exceptions(mock_run_cli: MagicMock):
    mock_run_cli.side_effect = RuntimeError("subprocess failed with /tmp/private")
    config = RunnableConfig(configurable={"session_id": "session-123"})

    msg = MagicMock()
    msg.tool_calls = [{"id": "call_1", "name": "get_architecture", "args": {}}]
    msg.invalid_tool_calls = []

    tools = [get_architecture]
    tool_messages = execute_tool_calls(msg, tools, config=config)

    assert len(tool_messages) == 1
    assert tool_messages[0].status == "error"
    assert "subprocess failed" not in tool_messages[0].content
    assert "Please try again." in tool_messages[0].content


@patch("app.agent.execute_tool_calls")
def test_call_tools_returns_clean_output(mock_execute_tool_calls: MagicMock):
    from app.agent import call_tools
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    mock_execute_tool_calls.return_value = [ToolMessage(content="Tool Output", tool_call_id="c1", name="search_code")]

    state: AgentState = {
        "messages": [
            HumanMessage(content="Find function"),
            AIMessage(content="", tool_calls=[{"name": "search_code", "args": {}, "id": "c1"}]),
        ]
    }

    res = call_tools(state, config=RunnableConfig())
    last_msg = res["messages"][-1]
    assert last_msg.content == "Tool Output"


@patch("app.agent._get_llm")
@patch("app.agent.settings")
def test_call_model_injects_budget_system_message(mock_settings: MagicMock, mock_get_llm: MagicMock):
    from app.agent import call_model
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    mock_settings.agent_max_tool_calls = 3
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    state: AgentState = {
        "messages": [
            HumanMessage(content="Find function"),
            AIMessage(content="", tool_calls=[{"name": "search_code", "args": {}, "id": "c1"}]),
        ]
    }

    call_model(state, config=RunnableConfig())

    mock_llm_with_tools.invoke.assert_called_once()
    invoked_msgs = mock_llm_with_tools.invoke.call_args[0][0]
    assert isinstance(invoked_msgs[-1], SystemMessage)
    assert "[System Info: You have 2 tool call turn(s) remaining" in invoked_msgs[-1].content


@patch("app.agent._get_llm")
@patch("app.agent.settings")
def test_call_model_unbinds_tools_when_exhausted(mock_settings: MagicMock, mock_get_llm: MagicMock):
    from app.agent import call_model
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    mock_settings.agent_max_tool_calls = 2
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    # 2 tool turns executed
    state: AgentState = {
        "messages": [
            HumanMessage(content="Search codebase"),
            AIMessage(content="", tool_calls=[{"name": "t1", "args": {}, "id": "1"}]),
            AIMessage(content="", tool_calls=[{"name": "t2", "args": {}, "id": "2"}]),
        ]
    }

    call_model(state, config=RunnableConfig())
    mock_llm.bind_tools.assert_not_called()
    mock_llm.invoke.assert_called_once()
    invoked_msgs = mock_llm.invoke.call_args[0][0]
    assert isinstance(invoked_msgs[-1], SystemMessage)
    assert "[System Info: You have 0 tool call turns remaining" in invoked_msgs[-1].content


@patch("app.agent.agent_executor.astream_events")
@patch("app.agent.agent_executor.aget_state")
def test_stream_chat_with_agent_emits_generic_error(mock_get_state: MagicMock, mock_astream_events: MagicMock):
    from app.agent import stream_chat_with_agent

    mock_state = MagicMock()
    mock_state.values = {"messages": []}
    mock_get_state.return_value = mock_state

    mock_astream_events.side_effect = RuntimeError("provider stack leaked /tmp/private")

    async def collect_events():
        events = []
        async for event in stream_chat_with_agent("session-stream-error", "Complex task"):
            events.append(event)
        return events

    events = asyncio.run(collect_events())
    assert events == [
        {
            "type": "error",
            "detail": "An error occurred while processing your request. Please try again.",
        }
    ]


def test_get_readme_content(tmp_path: Path):
    from app.utils import get_readme_content

    assert get_readme_content(None) == ""

    with patch("app.utils.settings.shared_data_dir", str(tmp_path)):
        assert get_readme_content("missing-session") == ""

        session_dir = tmp_path / "session-readme" / "repo"
        session_dir.mkdir(parents=True)

        readme_file = session_dir / "README.md"
        short_lines = [f"Line {i}" for i in range(1, 50)]
        readme_file.write_text("\n".join(short_lines), encoding="utf-8")

        res_short = get_readme_content("session-readme")
        assert res_short == "\n".join(short_lines)

        long_lines = [f"Line {i}" for i in range(1, 250)]
        readme_file.write_text("\n".join(long_lines), encoding="utf-8")

        res_long = get_readme_content("session-readme", max_lines=200)
        assert res_long.startswith("Line 1")
        assert "Line 200" in res_long
        assert "Line 201" not in res_long
        assert "... [README truncated at" in res_long
