import json
import os
import subprocess
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.config import settings
from app.file_access import MAX_TOOL_OUTPUT_BYTES, FileAccessError, SecureTextRead, read_secure_text_file
from app.logger import logger
from app.session import get_project_name_from_session_db, read_session_metadata, update_session_metadata
from app.utils import inject_project_prefix_to_cypher, run_isolated_subprocess, sanitize_string


def _resolve_project_name(session_id: str) -> str:
    """Retrieves and caches the indexed project name for a session."""
    cbm_cache_dir = Path(settings.shared_data_dir) / session_id
    if not cbm_cache_dir.exists():
        return ""

    meta = read_session_metadata(session_id)
    cached_project_name = meta.get("project_name")
    project_name = cached_project_name.strip() if isinstance(cached_project_name, str) else ""

    if not project_name:
        project_name = get_project_name_from_session_db(cbm_cache_dir) or ""
        if project_name:
            try:
                update_session_metadata(session_id, project_name=project_name)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to cache project name for session '{session_id}': {exc}")

    return project_name


def _run_cbm_cli(session_id: str | None, tool_name: str, args: list[str]) -> str:
    """Helper to execute the codebase-memory-mcp CLI against a session's isolated SQLite graph database."""
    if not session_id:
        logger.error(f"CBM CLI invocation failed: No session_id found in execution context. (tool={tool_name})")
        return "ERROR: No session_id found in execution context."

    cbm_cache_dir = Path(settings.shared_data_dir) / session_id
    if not cbm_cache_dir.exists():
        logger.error(
            f"CBM CLI invocation failed: Directory '{cbm_cache_dir}' does not exist for session '{session_id}'."
        )
        return f"ERROR: Knowledge graph data for session '{session_id}' not found. Has repository indexing completed?"

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "CBM_CACHE_DIR": str(cbm_cache_dir),
        "CBM_LOG_LEVEL": "error",
    }

    try:
        project_name = _resolve_project_name(session_id)

        if not project_name:
            logger.warning(f"CBM CLI invocation failed: No indexed project name found for session '{session_id}'.")
            return "ERROR: No indexed projects found in this session."

        cmd = ["codebase-memory-mcp", "cli", tool_name, "--project", project_name, "--json"] + args

        tool_result = run_isolated_subprocess(cmd, env=env, timeout=30)

        if tool_result.returncode != 0:
            raw_err = (tool_result.stderr or tool_result.stdout or "").strip()
            clean_err = sanitize_string(raw_err) if raw_err else "Graph engine execution failed."
            logger.error(
                f"CBM CLI command '{tool_name}' failed for project '{project_name}' (code {tool_result.returncode}): {clean_err}"
            )
            return f"ERROR: {clean_err}"

        # Unwrap MCP JSON structure if present
        try:
            out_data = json.loads(tool_result.stdout)
            if "content" in out_data and isinstance(out_data["content"], list) and len(out_data["content"]) > 0:
                raw_text = out_data["content"][0].get("text", tool_result.stdout)
                return sanitize_string(raw_text)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            logger.debug(f"Failed to unwrap MCP stdout JSON structure: {exc}")

        return sanitize_string(tool_result.stdout)

    except subprocess.TimeoutExpired:
        logger.error(f"CBM CLI command '{tool_name}' timed out for session '{session_id}'.")
        return "ERROR: Graph query timed out."
    except Exception as e:  # noqa: BLE001
        logger.error(f"Unexpected CLI execution error for session '{session_id}': {e}")
        return "ERROR: Internal execution error."


def get_saved_schema(session_id: str | None) -> str:
    """Reads saved graph schema from session directory, or fetches and saves it if missing."""
    if not session_id:
        return ""
    session_dir = Path(settings.shared_data_dir) / session_id
    schema_file = session_dir / "schema.json"
    if schema_file.exists():
        try:
            return schema_file.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to read schema file for session '{session_id}': {e}")

    # Fallback / generate schema
    schema = _run_cbm_cli(session_id, "get_graph_schema", [])
    if schema and not schema.startswith("ERROR:"):
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            schema_file.write_text(schema, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to save schema file for session '{session_id}': {e}")
    return schema


@tool
def get_architecture(config: RunnableConfig, path: str | None = None) -> str:
    """
    Get a high-level architectural overview of the repository.
    Use this tool FIRST when exploring a codebase to discover language distribution, entry points, HTTP routes, package structure, hotspots, and Leiden community clusters (architectural seams).

    Parameters:
    - path: Optional directory prefix to scope analysis (e.g. 'backend/app').
    """
    session_id = config.get("configurable", {}).get("session_id")
    args: list[str] = []
    if path:
        args.append(f"--path={path}")
    return _run_cbm_cli(session_id, "get_architecture", args)


@tool
def search_graph(
    config: RunnableConfig,
    query: str | None = None,
    name_pattern: str | None = None,
    label: str | None = None,
    file_pattern: str | None = None,
    limit: int = 15,
    offset: int = 0,
) -> str:
    """
    Search the codebase knowledge graph for functions, classes, routes, or variables.
    Use this tool instead of raw guessing to locate symbol definitions and exact qualified names.

    Parameters:
    - query: Natural-language or keyword full-text search with BM25 ranking (e.g. 'user authentication').
    - name_pattern: Regex pattern to match symbol names (e.g. '.*auth.*').
    - label: Filter by AST node label (e.g. 'Function', 'Class', 'Route', 'Variable', 'File').
    - file_pattern: Glob filter for source file paths.
    - limit: Maximum results to return (defaults to 15, capped at 50).
    - offset: Number of initial results to skip for pagination (defaults to 0).
    """
    session_id = config.get("configurable", {}).get("session_id")
    effective_limit = max(1, min(limit, 50))
    args: list[str] = []
    if query:
        args.append(f"--query={query}")
    if name_pattern:
        args.append(f"--name-pattern={name_pattern}")
    if label:
        args.append(f"--label={label}")
    if file_pattern:
        args.append(f"--file-pattern={file_pattern}")
    args.append(f"--limit={effective_limit}")
    if offset:
        args.append(f"--offset={offset}")
    return _run_cbm_cli(session_id, "search_graph", args)


@tool
def search_code(
    config: RunnableConfig,
    pattern: str,
    file_pattern: str | None = None,
    path_filter: str | None = None,
    mode: str = "compact",
    limit: int = 10,
) -> str:
    """
    Perform graph-augmented text search (grep enriched with knowledge graph metadata).
    Finds raw code string patterns, deduplicates matches into containing functions/classes, and ranks results by structural importance.

    Parameters:
    - pattern: Exact text string or regex pattern to search for in source code.
    - file_pattern: Glob filter for file inclusion (e.g., '*.py', '*.ts', '*.go').
    - path_filter: Regex filter on file paths (e.g., '^src/').
    - mode: Output mode — 'compact' (signatures + line context), 'full' (with source), or 'files' (file paths only).
    - limit: Maximum enriched function results to return (defaults to 10, capped at 50).
    """
    session_id = config.get("configurable", {}).get("session_id")
    effective_limit = max(1, min(limit, 50))
    args = [f"--pattern={pattern}"]
    if file_pattern:
        args.append(f"--file-pattern={file_pattern}")
    if path_filter:
        args.append(f"--path-filter={path_filter}")
    if mode:
        args.append(f"--mode={mode}")
    args.append(f"--limit={effective_limit}")
    return _run_cbm_cli(session_id, "search_code", args)


@tool
def trace_call_path(
    config: RunnableConfig,
    function_name: str | None = None,
    direction: str = "both",
    mode: str = "calls",
    depth: int = 3,
) -> str:
    """
    Trace paths through the code call graph.
    Use this to analyze caller/callee dependencies, data flows, or cross-service interactions.

    Parameters:
    - function_name: Name of the function or method to trace.
    - direction: 'inbound' (who calls this?), 'outbound' (who does this call?), or 'both' (default).
    - mode: 'calls' (follow function call edges), 'data_flow' (value propagation with arguments), or 'cross_service' (trace across HTTP/async routes).
    - depth: Hop depth limit (default 3, max 8).
    """
    session_id = config.get("configurable", {}).get("session_id")

    # Prepend project name if missing, since the DB requires the exact qualified_name
    if function_name and session_id:
        project_name = _resolve_project_name(session_id)
        if project_name and not function_name.startswith(f"{project_name}."):
            function_name = f"{project_name}.{function_name}"

    effective_depth = max(1, min(depth, 8))
    args = [
        f"--function-name={function_name or ''}",
        f"--direction={direction}",
        f"--mode={mode}",
        f"--depth={effective_depth}",
    ]
    return _run_cbm_cli(session_id, "trace_path", args)


def _format_snippet(code: str, target_type: str, target_label: str, start_line: int, num_lines: int) -> str:
    req_num = 200 if (num_lines is None or num_lines <= 0) else num_lines
    effective_num_lines = min(req_num, 400)

    lines = code.splitlines()
    total_lines = len(lines)

    if total_lines == 0:
        return f"[{target_type}: {target_label} | Showing lines 0-0 of 0 total lines]"

    start_idx = max(0, start_line - 1)
    if start_idx >= total_lines:
        start_idx = 0

    end_idx = min(start_idx + effective_num_lines, total_lines)
    actual_start_line = start_idx + 1
    actual_end_line = end_idx

    snippet = "\n".join(lines[start_idx:end_idx])
    header = f"[{target_type}: {target_label} | Showing lines {actual_start_line}-{actual_end_line} of {total_lines} total lines]"

    return f"{header}\n{snippet}"


def _format_secure_snippet(result: SecureTextRead, target_type: str, target_label: str) -> str:
    if result.total_lines == 0:
        header = f"[{target_type}: {target_label} | Showing lines 0-0 of 0 total lines]"
        return header

    header = f"[{target_type}: {target_label} | Showing lines {result.start_line}-{result.end_line} of {result.total_lines} total lines]"
    body = result.content
    if result.truncated:
        body = f"{body}\n... [output truncated]"
    return f"{header}\n{body}" if body else header


@tool
def get_code_snippet(
    config: RunnableConfig,
    qualified_name: str | None = None,
    file_path: str | None = None,
    start_line: int = 1,
    num_lines: int = 200,
) -> str:
    """
    Retrieve the exact source code for a function, class, symbol, or a specific file.
    You can either provide a `qualified_name` to get a symbol's definition, XOR a `file_path` to read raw file contents.
    Returns the requested snippet lines along with the total line count for the symbol or file.

    Parameters:
    - qualified_name: Full qualified name (e.g., 'app.api.chat') or short symbol name.
    - file_path: Relative path to the file in the repository (e.g., 'backend/app/main.py').
    - start_line: The line number to start reading from (1-indexed). Defaults to 1.
    - num_lines: The number of lines to read (defaults to 200, maximum capped at 400).
    """
    session_id = config.get("configurable", {}).get("session_id")

    if file_path:
        if not session_id:
            return "ERROR: No session_id found in execution context."

        repo_root = (Path(settings.shared_data_dir) / session_id / "repo").resolve()
        effective_num_lines = max(0, min(num_lines, 400))
        try:
            result = read_secure_text_file(
                repo_root,
                file_path,
                start_line=start_line,
                num_lines=effective_num_lines,
                max_output_bytes=MAX_TOOL_OUTPUT_BYTES,
            )
            return _format_secure_snippet(result, "File", file_path)
        except FileAccessError as e:
            logger.warning(
                "Secure file access denied for session '%s' and file '%s': %s", session_id, file_path, e.message
            )
            return f"Error: {e.message}"
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error reading file {file_path} for session {session_id}: {e}")
            return "Error: Failed to read file contents."

    # Fallback to CBM CLI for qualified symbol names
    # Prepend project name if missing, since the DB requires the exact qualified_name
    lookup_qn = qualified_name or ""
    if lookup_qn and session_id:
        project_name = _resolve_project_name(session_id)
        if project_name and not lookup_qn.startswith(f"{project_name}."):
            lookup_qn = f"{project_name}.{lookup_qn}"

    args = [f"--qualified-name={lookup_qn}"]
    raw_output = _run_cbm_cli(session_id, "get_code_snippet", args)

    if not raw_output or raw_output.startswith(("ERROR:", "Error:")):
        return raw_output

    code_text = raw_output
    try:
        parsed = json.loads(raw_output)
        if isinstance(parsed, dict) and "source" in parsed and isinstance(parsed["source"], str):
            code_text = parsed["source"]
    except (json.JSONDecodeError, TypeError):
        pass

    return _format_snippet(code_text, "Symbol", qualified_name or "", start_line, num_lines)


@tool
def query_graph(config: RunnableConfig, cypher_query: str | None = None, max_rows: int = 100) -> str:
    """
    Execute a read-only openCypher query against the codebase knowledge graph for complex multi-hop analysis, metrics, or graph traversals.
    Example: MATCH (f:Function)-[:CALLS]->(g:Function) WHERE f.name = 'chat' RETURN f.name AS from, g.name AS to

    IMPORTANT CYPHER LIMITATIONS:
    - Named path assignment (e.g., `MATCH p=(a)-... RETURN p`) is NOT supported. Do not use `p=`.
    - DO NOT use Cypher/SQL reserved keywords as aliases (e.g., avoid AS from, AS limit, AS match). Instead, use safe identifiers like AS source, AS target, AS caller, or AS callee.

    Parameters:
    - cypher_query: The openCypher query string to execute.
    - max_rows: Maximum rows to return (defaults to 100, capped at 100).
    """
    session_id = config.get("configurable", {}).get("session_id")
    effective_max_rows = max(1, min(max_rows, 100))

    if cypher_query and session_id:
        project_name = _resolve_project_name(session_id)
        if project_name:
            cypher_query = inject_project_prefix_to_cypher(cypher_query, project_name)

    args = [f"--query={cypher_query or ''}", f"--max-rows={effective_max_rows}"]
    return _run_cbm_cli(session_id, "query_graph", args)
