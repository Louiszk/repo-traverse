import errno
import logging
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import tiktoken
from fastapi import Request
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.config import settings

logger = logging.getLogger(__name__)


def run_isolated_subprocess(
    cmd: list[str],
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Runs a subprocess and kills its whole process group on interruption or timeout."""
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stderr_file,
    ):
        kwargs: dict[str, Any] = {
            "stdout": stdout_file,
            "stderr": stderr_file,
            "env": env,
        }

        if sys.platform != "win32":
            kwargs["start_new_session"] = True

        process = subprocess.Popen(cmd, **kwargs)

        def kill_process_tree() -> None:
            try:
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            except OSError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree()
            process.wait()
            raise
        except BaseException:
            kill_process_tree()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("Subprocess did not terminate cleanly after process-group kill.")
            raise

        stdout_file.seek(0)
        stderr_file.seek(0)
        # Prevent memory exhaustion by reading at most 1MB (~1 million chars)
        stdout_str = stdout_file.read(1_000_000)
        stderr_str = stderr_file.read(1_000_000)

    return subprocess.CompletedProcess(cmd, process.returncode, stdout_str, stderr_str)


def extract_text_content(content: Any) -> str:
    """Extracts plain text string from message content, ignoring non-text blocks like function calls and reasoning."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                text_val = block.get("text")
                block_type = block.get("type")
                if (
                    block_type == "text"
                    and text_val is not None
                    or text_val is not None
                    and block_type not in ("reasoning", "function_call", "tool_use", "tool_call")
                ):
                    text_parts.append(str(text_val))
            elif hasattr(block, "text") and block.text is not None:
                block_type = getattr(block, "type", None)
                if block_type not in ("reasoning", "function_call", "tool_use", "tool_call"):
                    text_parts.append(str(block.text))
        return "".join(text_parts)

    if isinstance(content, dict):
        text_val = content.get("text")
        block_type = content.get("type")
        if (
            block_type == "text"
            and text_val is not None
            or text_val is not None
            and block_type not in ("reasoning", "function_call", "tool_use", "tool_call")
        ):
            return str(text_val)

    return ""


def count_tool_turns(messages: list[BaseMessage]) -> int:
    """Counts the number of AI model messages containing tool calls sent since the last HumanMessage."""
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    turn_messages = messages[last_human_idx + 1 :] if last_human_idx != -1 else messages
    return sum(1 for msg in turn_messages if getattr(msg, "tool_calls", None))


def get_token_count(text_or_messages: str | BaseMessage | Sequence[BaseMessage | str] | None) -> int:
    """Calculates tiktoken token count for a text string, single message, or list of messages."""
    if text_or_messages is None:
        return 0
    try:
        encoding = tiktoken.get_encoding(settings.tokenizer_encoding)
    except Exception:  # noqa: BLE001
        encoding = None

    def _count_str(s: str) -> int:
        if not s:
            return 0
        if encoding:
            return len(encoding.encode(s))
        return len(s) // 4

    if isinstance(text_or_messages, str):
        return _count_str(text_or_messages)

    if isinstance(text_or_messages, BaseMessage):
        msgs = [text_or_messages]
    elif isinstance(text_or_messages, (list, tuple)):
        msgs = list(text_or_messages)
    else:
        return _count_str(str(text_or_messages))

    total = 0
    for item in msgs:
        if isinstance(item, str):
            total += _count_str(item)
        elif isinstance(item, BaseMessage):
            total += 4
            content_str = extract_text_content(item.content) if hasattr(item, "content") else str(item)
            total += _count_str(content_str)
            tool_calls = getattr(item, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        total += _count_str(str(tc.get("name", "")))
                        total += _count_str(str(tc.get("args", {})))
        else:
            total += _count_str(str(item))

    return total


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncates string to at most max_tokens using configured tiktoken encoding."""
    if not text or max_tokens <= 0:
        return ""
    encoding = tiktoken.get_encoding(settings.tokenizer_encoding)
    if encoding is None:
        return text[: max_tokens * 4]
    try:
        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens]
        return encoding.decode(truncated_tokens, errors="ignore")
    except Exception:  # noqa: BLE001
        return text[: max_tokens * 4]


def execute_tool_calls(
    message: BaseMessage,
    tools: Sequence[BaseTool],
    config: RunnableConfig | None = None,
) -> list[ToolMessage]:
    """
    Executes tool calls extracted from an LLM response message sequentially.
    Supports invalid call handling and RunnableConfig propagation.
    """
    tool_map = {tool.name: tool for tool in tools}
    tool_messages: list[ToolMessage] = []

    # 1. Handle invalid tool calls generated by LLM
    invalid_calls = getattr(message, "invalid_tool_calls", []) or []
    for invalid_call in invalid_calls:
        if isinstance(invalid_call, dict):
            cid = invalid_call.get("id")
            name = invalid_call.get("name")
        else:
            cid = getattr(invalid_call, "id", None)
            name = getattr(invalid_call, "name", None)

        logger.warning("Invalid tool call received for '%s'", name or "unknown")
        content = f"Error: Failed to parse tool call for '{name or 'unknown'}'. Please fix your tool call format."
        tool_messages.append(
            ToolMessage(
                content=content,
                tool_call_id=str(cid) if cid else "unknown",
                name=name or "unknown",
                status="error",
            )
        )

    # 2. Extract valid tool calls
    tool_calls = getattr(message, "tool_calls", []) or []
    if not tool_calls:
        return tool_messages

    # 3. Sequential execution of tool calls
    for call in tool_calls:
        call_id = str(call.get("id", "unknown"))
        name = call.get("name", "")
        args = call.get("args", {}) or {}

        if not name:
            logger.warning("Malformed tool call missing tool name")
            tool_messages.append(
                ToolMessage(
                    content="Error: Malformed tool call missing tool name.",
                    tool_call_id=call_id,
                    name="unknown",
                    status="error",
                )
            )
            continue

        target_tool = tool_map.get(name)
        if not target_tool:
            logger.warning("Invalid tool requested: %s", name)
            tool_messages.append(
                ToolMessage(
                    content=f"Error: '{name}' is not a valid tool.",
                    tool_call_id=call_id,
                    name=name,
                    status="error",
                )
            )
            continue

        try:
            sanitized_args = sanitize_tool_args(args)
            logger.debug(f"Executing tool '{name}' with args {sanitized_args}")
            res = target_tool.invoke(sanitized_args, config=config)
            content = str(res) if res is not None else f"Tool '{name}' executed successfully."
            sanitized_content = sanitize_string(content)
            tool_messages.append(ToolMessage(content=sanitized_content, tool_call_id=call_id, name=name))
        except Exception as exc:
            logger.exception("Error executing tool '%s'", name)
            err_msg = f"Error executing tool '{name}'. Please try again."
            tool_messages.append(
                ToolMessage(content=sanitize_string(err_msg), tool_call_id=call_id, name=name, status="error")
            )

    return tool_messages


def sanitize_string(text: Any) -> str:
    """Strips internal app-data-session-xxx-repo repository prefixes from a string."""
    if not text or not isinstance(text, str):
        return "" if text is None else str(text)
    pattern = r"app-data-(?:scratch-)?session-[a-fA-F0-9\-]+-repo[/\.\\]?"
    return re.sub(pattern, "", text)


def sanitize_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Strips internal system parameters and cleans string values in tool arguments."""
    if not isinstance(args, dict):
        return {}
    ignored_keys = {"config", "session_id", "thread_id", "configurable", "project", "project_name", "session"}
    sanitized: dict[str, Any] = {}
    for k, v in args.items():
        if k in ignored_keys or k.startswith("_"):
            continue
        if isinstance(v, str):
            cleaned_v = sanitize_string(v)
            if not cleaned_v and ("app-data-" in v or "session-" in v):
                continue
            sanitized[k] = cleaned_v
        else:
            sanitized[k] = v
    return sanitized


def get_client_ip(request: Request) -> str:
    """Extracts real IP strictly based on the environment's proxy topology."""
    if settings.is_production:
        # Production: We are strictly behind Cloudflare. Trust only CF-Connecting-IP.
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        logger.warning(
            "CF-Connecting-IP header missing in production request.",
            extra={"extra_fields": {"request_method": request.method, "request_path": request.url.path}},
        )

    else:
        # Development: Trust the last hop appended by the local Nginx container.
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[-1].strip()

    # Ultimate fallback (will return Nginx's internal Docker IP in prod if headers are missing)
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def handle_remove_readonly(func: Any, path: str | Path, exc_info: Any) -> None:
    """Error handler for shutil.rmtree to remove read-only files."""
    exc = exc_info[1] if isinstance(exc_info, tuple) else exc_info
    if isinstance(exc, FileNotFoundError) or (isinstance(exc, OSError) and exc.errno == errno.ENOENT):
        return
    if not isinstance(exc, OSError) or exc.errno not in {errno.EACCES, errno.EPERM}:
        raise exc

    try:
        Path(path).chmod(stat.S_IWRITE)
        func(path)
    except FileNotFoundError:
        pass


_README_CANDIDATES = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "readme.md",
    "readme.rst",
    "readme.txt",
]


def get_readme_content(session_id: str | None, max_lines: int = 200) -> str:
    """Reads the repository README from the session repo directory, truncated to max_lines."""
    if not session_id:
        return ""

    repo_root = Path(settings.shared_data_dir) / session_id / "repo"
    if not repo_root.exists():
        return ""

    for candidate in _README_CANDIDATES:
        readme_path = repo_root / candidate
        if readme_path.is_file():
            try:
                with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(64 * 1024)  # Read at most 64KB
                lines = content.splitlines()
                if len(lines) > max_lines:
                    content = (
                        "\n".join(lines[:max_lines])
                        + f"\n... [README truncated at {max_lines} lines. Use get_code_snippet tool to read more if needed.]"
                    )
                return content.strip()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to read README for session '{session_id}': {e}")
                return ""

    return ""


def inject_project_prefix_to_cypher(cypher_query: str, project_name: str) -> str:
    """
    Injects the project prefix into exact qualified_name lookups in a Cypher query.
    Matches `{qualified_name: '...'}` or `f.qualified_name = "..."`.
    """
    if not cypher_query or not project_name:
        return cypher_query or ""

    def _inject_qn(match: re.Match[str]) -> str:
        full_match = match.group(0)
        quote = match.group(1)
        qn = match.group(2)

        if not qn or qn.startswith(f"{project_name}."):
            return full_match

        prefix_part = full_match[: full_match.find(quote) + 1]
        return f"{prefix_part}{project_name}.{qn}{quote}"

    pattern = r"qualified_name\s*(?:=|:)\s*(['\"])(.*?)\1"
    return re.sub(pattern, _inject_qn, cypher_query)
