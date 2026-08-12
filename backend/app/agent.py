import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.checkpoint import RedisSaver
from app.config import settings
from app.prompts import get_system_prompt
from app.session import read_session_metadata
from app.tools import (
    get_architecture,
    get_code_snippet,
    get_saved_schema,
    query_graph,
    search_code,
    search_graph,
    trace_call_path,
)
from app.tracing import SessionTracer
from app.utils import (
    count_tool_turns,
    execute_tool_calls,
    extract_text_content,
    get_readme_content,
    get_token_count,
    sanitize_string,
    sanitize_tool_args,
    truncate_to_tokens,
)

logger = logging.getLogger(__name__)

tools = [
    get_architecture,
    search_graph,
    search_code,
    trace_call_path,
    get_code_snippet,
    query_graph,
]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _get_llm() -> ChatOpenAI:
    """Helper to instantiate ChatOpenAI using application settings."""
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        reasoning_effort=settings.reasoning_effort,
        max_completion_tokens=settings.max_completion_tokens,
        use_responses_api=True,
        stream_usage=True,
        timeout=40.0,
    )


def _get_safe_context_limit() -> int:
    """Returns calculated safe context token limit, handling mocks cleanly."""
    raw_ctx = settings.max_context_tokens
    raw_comp = settings.max_completion_tokens

    max_ctx = int(raw_ctx) if isinstance(raw_ctx, (int, float)) else 128000
    max_comp = int(raw_comp) if isinstance(raw_comp, (int, float)) else 20000

    return max_ctx - max_comp - 2000


def call_model(state: AgentState, config: RunnableConfig) -> dict[str, list[BaseMessage]]:
    """Invokes LLM bound with tools if budget and context space remain, else invokes LLM without tools."""
    llm = _get_llm()
    messages = state.get("messages", [])
    executed_turns = count_tool_turns(messages)
    remaining = max(0, settings.agent_max_tool_calls - executed_turns)

    current_tokens = get_token_count(messages)
    safe_limit = _get_safe_context_limit()

    context_limit_reached = current_tokens > safe_limit or any(
        "Context window limit reached" in extract_text_content(getattr(m, "content", "")) for m in messages[-6:]
    )

    if context_limit_reached:
        info_note = (
            "[System Info: Context window limit reached. "
            "Please summarize your findings and provide your final response to the user now.]"
        )
    elif remaining <= 0:
        info_note = (
            "[System Info: You have 0 tool call turns remaining for this user request. "
            "Please summarize your findings and provide your final response to the user now.]"
        )
    else:
        info_note = (
            f"[System Info: You have {remaining} tool call turn(s) remaining for this user request. "
            "You do not have to use all remaining tool calls if you already have enough information.]"
        )

    invocation_messages = list(messages) + [SystemMessage(content=info_note)]

    if executed_turns >= settings.agent_max_tool_calls or context_limit_reached:
        logger.info(
            f"Bypassing tool binding (executed_turns={executed_turns}, context_limit_reached={context_limit_reached})."
        )
        response = llm.invoke(invocation_messages, config=config)
    else:
        llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=False)
        response = llm_with_tools.invoke(invocation_messages, config=config)

    return {"messages": [response]}


def call_tools(state: AgentState, config: RunnableConfig) -> dict[str, list[BaseMessage]]:
    """Executes tool calls, truncates output per limits, checks context window safety, and returns tool messages."""
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
    last_message = messages[-1]
    tool_messages: list[BaseMessage] = list(execute_tool_calls(last_message, tools, config=config))

    # Truncate each individual tool output to max_context_tokens // 4
    raw_ctx = settings.max_context_tokens
    max_ctx = int(raw_ctx) if isinstance(raw_ctx, (int, float)) else 128000
    max_indiv_tokens = max_ctx // 4

    for tm in tool_messages:
        content_str = extract_text_content(tm.content)
        if get_token_count(content_str) > max_indiv_tokens:
            tm.content = truncate_to_tokens(content_str, max_indiv_tokens) + "\n... [Output truncated]"

    # Before wrapping/returning, calculate projected total token count
    total_tokens = get_token_count(messages) + get_token_count(tool_messages)
    safe_limit = _get_safe_context_limit()

    if total_tokens > safe_limit:
        logger.warning(
            f"Projected total tokens ({total_tokens}) exceed safe limit ({safe_limit}). Discarding tool outputs."
        )
        for tm in tool_messages:
            tm.content = (
                "Error: Tool output discarded. Context window limit reached. "
                "You must now summarize your findings and provide a final response without using more tools."
            )
            if isinstance(tm, ToolMessage):
                tm.status = "error"

    return {"messages": tool_messages}


def should_continue(state: AgentState) -> str:
    """Conditional edge router: proceeds to tools if tool calls exist, else END."""
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "end"


workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
workflow.add_edge("tools", "agent")

memory = RedisSaver()
agent_executor = workflow.compile(checkpointer=memory)


def get_human_message_count(session_id: str) -> int:
    """Returns the number of HumanMessages in the current session memory."""
    config = RunnableConfig(configurable={"thread_id": session_id, "session_id": session_id})
    state = agent_executor.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    return sum(1 for msg in messages if isinstance(msg, HumanMessage))


def get_session_token_count(session_id: str) -> int:
    """Returns total token count of existing messages in session memory."""
    config = RunnableConfig(configurable={"thread_id": session_id, "session_id": session_id})
    state = agent_executor.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    return get_token_count(messages)


MAX_TOOL_OUTPUT_CHARS = 50_000


def _truncate_output(text: str) -> str:
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        return text[:MAX_TOOL_OUTPUT_CHARS] + "\n... [Output truncated]"
    return text


async def stream_chat_with_agent(session_id: str, user_message: str) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator streaming tool call events and final response."""
    tracer = SessionTracer(session_id, user_message)
    final_reply = ""

    config = RunnableConfig(
        configurable={"thread_id": session_id, "session_id": session_id},
        recursion_limit=settings.agent_max_tool_calls * 2 + 5,
    )

    state = await agent_executor.aget_state(config)
    messages: list[BaseMessage] = []

    if not state.values.get("messages"):
        schema_data = get_saved_schema(session_id)
        meta = read_session_metadata(session_id)
        repo_slug = meta.get("repo_slug", "")
        readme_content = get_readme_content(session_id)
        messages.append(
            SystemMessage(
                content=get_system_prompt(
                    graph_schema=schema_data,
                    repo_slug=repo_slug if isinstance(repo_slug, str) else "",
                    readme_content=readme_content,
                )
            )
        )
    messages.append(HumanMessage(content=user_message))

    tool_calls_executed: list[dict[str, Any]] = []

    try:
        async for event in agent_executor.astream_events({"messages": messages}, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name")

            if kind == "on_chat_model_start":
                tracer.start_turn()

            elif kind == "on_chat_model_stream":
                tracer.record_ttft()
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    content = getattr(chunk, "content", "")
                    delta = extract_text_content(content)
                    if delta:
                        yield {"type": "token", "delta": delta}

            elif kind == "on_tool_start":
                raw_args = event.get("data", {}).get("input", {})
                clean_args = sanitize_tool_args(raw_args)
                tracer.start_tool(name, raw_args)
                tool_info = {"name": name, "args": clean_args, "output": "", "status": "running"}
                tool_calls_executed.append(tool_info)
                yield {"type": "tool_start", "tool": name, "args": clean_args}

            elif kind == "on_tool_end":
                output = event.get("data", {}).get("output")
                status = "success"
                error_str = None
                output_content = ""
                if isinstance(output, ToolMessage):
                    output_content = extract_text_content(output.content)
                    if getattr(output, "status", None) == "error" or str(output.content).startswith("Error:"):
                        status = "failure"
                        error_str = str(output.content)
                elif isinstance(output, str):
                    output_content = output
                    if output.startswith("Error:"):
                        status = "failure"
                        error_str = output
                elif output is not None:
                    output_content = str(output)

                tracer.end_tool(name, status=status, error=error_str)
                tool_status = "error" if status == "failure" else "done"
                sanitized_output = _truncate_output(sanitize_string(output_content))
                if tool_calls_executed and tool_calls_executed[-1]["name"] == name:
                    tool_calls_executed[-1]["output"] = sanitized_output
                    tool_calls_executed[-1]["status"] = tool_status
                yield {"type": "tool_end", "tool": name, "status": tool_status, "output": sanitized_output}

            elif kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if output:
                    usage = getattr(output, "usage_metadata", None)
                    tracer.end_llm_turn(usage)

            elif kind == "on_chain_end" and name == "LangGraph":
                output = event.get("data", {}).get("output", {})
                final_msgs = output.get("messages", []) if isinstance(output, dict) else []
                if final_msgs:
                    final_reply = extract_text_content(final_msgs[-1].content)

                safe_limit = _get_safe_context_limit()
                is_context_full = get_token_count(final_msgs) >= safe_limit or any(
                    "Context window limit reached" in extract_text_content(getattr(m, "content", ""))
                    for m in final_msgs
                )

                yield {
                    "type": "final_reply",
                    "reply": final_reply,
                    "tool_calls": tool_calls_executed,
                    "is_context_full": is_context_full,
                }
    except GraphRecursionError as gre:
        logger.warning(f"Graph recursion limit reached for session {session_id}: {gre}")
        err_msg = "An error occurred while processing your request. Please try again."
        tracer.set_fatal_error(err_msg)
        yield {
            "type": "error",
            "detail": err_msg,
        }
    except Exception:
        logger.exception(f"Agent execution error for session {session_id}")
        err_msg = "An error occurred while processing your request. Please try again."
        tracer.set_fatal_error(err_msg)
        yield {
            "type": "error",
            "detail": err_msg,
        }
    finally:
        tracer.finalize(final_reply)
