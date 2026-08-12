from app.utils import (
    count_tool_turns,
    extract_text_content,
    inject_project_prefix_to_cypher,
    sanitize_string,
    sanitize_tool_args,
    truncate_to_tokens,
)


def test_inject_project_prefix_to_cypher_single_quotes():
    query = "MATCH (f:Function {qualified_name:'main_api.views.AgentViewSet.create'}) RETURN f"
    project = "app-data-session-123-repo"
    expected = (
        "MATCH (f:Function {qualified_name:'app-data-session-123-repo.main_api.views.AgentViewSet.create'}) RETURN f"
    )
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_double_quotes():
    query = 'MATCH (f:Function {qualified_name: "main_api.views.AgentViewSet.create"}) RETURN f'
    project = "app-data-session-123-repo"
    expected = (
        'MATCH (f:Function {qualified_name: "app-data-session-123-repo.main_api.views.AgentViewSet.create"}) RETURN f'
    )
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_equality():
    query = "MATCH (f:Function) WHERE f.qualified_name = 'main_api.views.AgentViewSet.create' RETURN f"
    project = "app-data-session-123-repo"
    expected = "MATCH (f:Function) WHERE f.qualified_name = 'app-data-session-123-repo.main_api.views.AgentViewSet.create' RETURN f"
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_no_spaces():
    query = "MATCH (f:Function {qualified_name:'main_api.views'}) RETURN f"
    project = "app-data-session-123-repo"
    expected = "MATCH (f:Function {qualified_name:'app-data-session-123-repo.main_api.views'}) RETURN f"
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_already_has_prefix():
    query = "MATCH (f:Function) WHERE f.qualified_name = 'app-data-session-123-repo.main_api.views' RETURN f"
    project = "app-data-session-123-repo"
    expected = "MATCH (f:Function) WHERE f.qualified_name = 'app-data-session-123-repo.main_api.views' RETURN f"
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_empty_string():
    query = "MATCH (f:Function {qualified_name: ''}) RETURN f"
    project = "app-data-session-123-repo"
    expected = "MATCH (f:Function {qualified_name: ''}) RETURN f"
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_inject_project_prefix_to_cypher_multiple_matches():
    query = "MATCH (f:Function {qualified_name: 'foo'}), (g:Function {qualified_name: 'bar'}) RETURN f, g"
    project = "project"
    expected = (
        "MATCH (f:Function {qualified_name: 'project.foo'}), (g:Function {qualified_name: 'project.bar'}) RETURN f, g"
    )
    assert inject_project_prefix_to_cypher(query, project) == expected


def test_sanitize_string():
    assert sanitize_string("app-data-scratch-session-123-repo.main_api") == "main_api"
    assert sanitize_string("app-data-session-456-repo/src/index.ts") == "src/index.ts"
    assert sanitize_string("app-data-scratch-session-abc-repo\\backend") == "backend"
    assert sanitize_string("normal_string_without_prefix") == "normal_string_without_prefix"
    assert sanitize_string("") == ""
    assert sanitize_string(None) == ""


def test_sanitize_tool_args():
    args = {
        "function_name": "app-data-scratch-session-123-repo.main_api",
        "config": "should_be_ignored",
        "session_id": "123",
        "normal_arg": "value",
        "_private_arg": "hidden",
        "int_arg": 42,
    }

    sanitized = sanitize_tool_args(args)

    # Should strip prefix from string values
    assert sanitized["function_name"] == "main_api"

    # Should ignore system keys
    assert "config" not in sanitized
    assert "session_id" not in sanitized
    assert "_private_arg" not in sanitized

    # Should keep normal args untouched
    assert sanitized["normal_arg"] == "value"
    assert sanitized["int_arg"] == 42


def test_truncate_to_tokens():
    text = "hello world this is a test"
    # Assuming 'hello world this is a test' is ~6 tokens

    # If max_tokens is very large, it should return the full text
    assert truncate_to_tokens(text, 100) == text

    # If max_tokens is 0, it should return empty string
    assert truncate_to_tokens(text, 0) == ""

    # If max_tokens truncates the text, it should return a shorter string
    truncated = truncate_to_tokens(text, 2)
    assert len(truncated) > 0
    assert len(truncated) < len(text)
    assert text.startswith(truncated)


def test_extract_text_content():
    # String content
    assert extract_text_content("Simple response") == "Simple response"

    # List of content blocks from Responses API (reasoning + text)
    blocks = [
        {"id": "rs_123", "type": "reasoning", "content": [], "encrypted_content": "secret"},
        {"type": "text", "text": "Extracted answer", "annotations": []},
    ]
    assert extract_text_content(blocks) == "Extracted answer"

    # List of string parts
    assert extract_text_content(["Hello ", "world"]) == "Hello world"

    # Function call blocks should return empty string, not stringified python representation
    fc_blocks = [{"type": "function_call", "arguments": "-data", "index": 1}]
    assert extract_text_content(fc_blocks) == ""

    # None and empty structures
    assert extract_text_content(None) == ""
    assert extract_text_content([]) == ""
    assert extract_text_content({}) == ""


def test_count_tool_turns():
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    messages = [
        SystemMessage(content="sys"),
        HumanMessage(content="turn 1"),
        AIMessage(content="", tool_calls=[{"name": "t1", "args": {}, "id": "1"}]),
        AIMessage(content="res turn 1"),
        HumanMessage(content="turn 2"),
        AIMessage(content="", tool_calls=[{"name": "t2", "args": {}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "t3", "args": {}, "id": "3"}]),
    ]

    assert count_tool_turns(messages) == 2
