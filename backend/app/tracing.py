import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.redis_client import get_redis_client
from app.utils import sanitize_tool_args

logger = logging.getLogger(__name__)


# Note: This is only correct for the OpenAI API
def calculate_token_cost(input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
    """Calculates dollar cost for a set of token counts based on model pricing settings."""
    standard_input = max(0, input_tokens - cached_input_tokens)
    return (
        standard_input * settings.cost_input_tokens
        + cached_input_tokens * settings.cost_cached_input_tokens
        + output_tokens * settings.cost_output_tokens
    ) / 1_000_000.0


def record_token_usage(usage: dict | None) -> None:
    """Calculates dollar cost based on token usage and increments global Redis budget."""
    if not usage:
        return

    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    input_token_details = usage.get("input_token_details", {}) or {}
    cache_read = int(input_token_details.get("cache_read", 0))

    cost = calculate_token_cost(input_tokens, cache_read, output_tokens)

    if cost > 0:
        client = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cost_key = f"global_cost:{today}"
        client.incrbyfloat(cost_key, cost)
        client.expire(cost_key, 86400 * 30)


def sanitize_trace_args(args: Any, max_str_len: int = 200) -> Any:
    """Sanitizes tool arguments and truncates long string values to prevent prompt/data leakage in traces."""
    if isinstance(args, dict):
        cleaned = sanitize_tool_args(args)
        return {k: sanitize_trace_args(v, max_str_len) for k, v in cleaned.items()}
    elif isinstance(args, list):
        return [sanitize_trace_args(item, max_str_len) for item in args]
    elif isinstance(args, str):
        if len(args) > max_str_len:
            return args[:max_str_len] + "..."
        return args
    return args


class SessionTracer:
    """Encapsulates execution tracing for a single user interaction session."""

    def __init__(self, session_id: str, user_message: str):
        self.session_id = session_id
        self.interaction_id = f"req_{uuid.uuid4().hex[:8]}"
        self.start_timestamp = datetime.now(timezone.utc).isoformat()
        self.start_time = time.time()
        self.user_message_len = len(user_message or "")
        self.final_reply_len = 0
        self.fatal_error: str | None = None

        self.overall_tokens = {
            "input": 0,
            "cached_input": 0,
            "output": 0,
            "reasoning": 0,
        }
        self.total_cost_usd = 0.0
        self.turns: list[dict[str, Any]] = []

        self.current_turn: dict[str, Any] | None = None

    def start_turn(self) -> dict[str, Any]:
        """Starts a new LLM reasoning turn."""
        turn_index = len(self.turns) + 1
        turn = {
            "turn_index": turn_index,
            "llm_metrics": {
                "ttft_ms": None,
                "latency_ms": 0,
            },
            "tokens": {
                "input": 0,
                "cached_input": 0,
                "output": 0,
            },
            "cache_hit_rate": 0.0,
            "tools": [],
            "turn_error": None,
            "_start_time": time.time(),
            "_ttft_time": None,
        }
        self.current_turn = turn
        self.turns.append(turn)
        return turn

    def record_ttft(self) -> None:
        """Records Time To First Token for current turn if not already set."""
        if self.current_turn and self.current_turn["_ttft_time"] is None:
            self.current_turn["_ttft_time"] = time.time()
            start_t = self.current_turn["_start_time"]
            ttft_ms = round((self.current_turn["_ttft_time"] - start_t) * 1000, 2)
            self.current_turn["llm_metrics"]["ttft_ms"] = ttft_ms

    def end_llm_turn(self, usage_metadata: dict[str, Any] | None) -> None:
        """Completes LLM execution for current turn and accumulates usage metrics."""
        if not self.current_turn:
            return

        end_time = time.time()
        start_time = self.current_turn["_start_time"]
        self.current_turn["llm_metrics"]["latency_ms"] = round((end_time - start_time) * 1000, 2)

        if usage_metadata:
            input_tokens = int(usage_metadata.get("input_tokens", 0))
            output_tokens = int(usage_metadata.get("output_tokens", 0))

            input_token_details = usage_metadata.get("input_token_details", {}) or {}
            cached_input = int(input_token_details.get("cache_read", 0))

            output_token_details = usage_metadata.get("output_token_details", {}) or {}
            reasoning_tokens = int(output_token_details.get("reasoning", 0))

            self.current_turn["tokens"]["input"] = input_tokens
            self.current_turn["tokens"]["cached_input"] = cached_input
            self.current_turn["tokens"]["output"] = output_tokens

            cache_rate = (cached_input / input_tokens) if input_tokens > 0 else 0.0
            self.current_turn["cache_hit_rate"] = round(cache_rate, 4)

            self.overall_tokens["input"] += input_tokens
            self.overall_tokens["cached_input"] += cached_input
            self.overall_tokens["output"] += output_tokens
            self.overall_tokens["reasoning"] += reasoning_tokens

            turn_cost = calculate_token_cost(input_tokens, cached_input, output_tokens)
            self.total_cost_usd += turn_cost

            record_token_usage(usage_metadata)

    def start_tool(self, tool_name: str, tool_args: dict[str, Any] | None) -> None:
        """Records tool call start within current turn."""
        turn = self.current_turn or self.start_turn()

        sanitized_args = sanitize_trace_args(tool_args or {})
        tool_entry = {
            "name": tool_name,
            "args": sanitized_args,
            "latency_ms": None,
            "status": "success",
            "error": None,
            "_start_time": time.time(),
        }
        turn["tools"].append(tool_entry)

    def end_tool(self, tool_name: str, status: str = "success", error: str | None = None) -> None:
        """Records tool call completion/failure within current turn."""
        if not self.current_turn:
            return

        end_time = time.time()
        for tool_entry in reversed(self.current_turn["tools"]):
            if tool_entry["name"] == tool_name and tool_entry["latency_ms"] is None:
                start_time = tool_entry.get("_start_time", end_time)
                tool_entry["latency_ms"] = round((end_time - start_time) * 1000, 2)
                tool_entry["status"] = status
                tool_entry["error"] = error
                break

    def record_turn_error(self, error: str) -> None:
        """Records error on the current active turn."""
        if self.current_turn:
            self.current_turn["turn_error"] = error

    def set_fatal_error(self, error: str) -> None:
        """Records fatal error for interaction."""
        self.fatal_error = error

    def finalize(self, final_reply: str = "") -> None:
        """Constructs final JSON trace object and appends it to traces/<session_id>.jsonl."""
        try:
            total_latency_ms = round((time.time() - self.start_time) * 1000, 2)
            self.final_reply_len = len(final_reply or "")

            overall_input = self.overall_tokens["input"]
            overall_cached = self.overall_tokens["cached_input"]
            overall_cache_hit_rate = round((overall_cached / overall_input) if overall_input > 0 else 0.0, 4)

            cleaned_turns = []
            for turn in self.turns:
                t_copy = {
                    "turn_index": turn["turn_index"],
                    "llm_metrics": {
                        "ttft_ms": turn["llm_metrics"]["ttft_ms"],
                        "latency_ms": turn["llm_metrics"]["latency_ms"],
                    },
                    "tokens": {
                        "input": turn["tokens"]["input"],
                        "cached_input": turn["tokens"]["cached_input"],
                        "output": turn["tokens"]["output"],
                    },
                    "cache_hit_rate": turn["cache_hit_rate"],
                    "tools": [
                        {
                            "name": tool["name"],
                            "args": tool["args"],
                            "latency_ms": tool["latency_ms"] if tool["latency_ms"] is not None else 0.0,
                            "status": tool["status"],
                            "error": tool["error"],
                        }
                        for tool in turn["tools"]
                    ],
                    "turn_error": turn["turn_error"],
                }
                cleaned_turns.append(t_copy)

            trace_record = {
                "interaction_id": self.interaction_id,
                "timestamp": self.start_timestamp,
                "meta": {
                    "user_message_length_chars": self.user_message_len,
                    "final_reply_length_chars": self.final_reply_len,
                },
                "overall_metrics": {
                    "total_latency_ms": total_latency_ms,
                    "total_cost_usd": round(self.total_cost_usd, 6),
                    "total_tokens": self.overall_tokens,
                    "overall_cache_hit_rate": overall_cache_hit_rate,
                },
                "turns": cleaned_turns,
                "fatal_error": self.fatal_error,
            }

            traces_dir = Path(settings.shared_data_dir) / "traces"
            traces_dir.mkdir(parents=True, exist_ok=True)
            trace_file = traces_dir / f"{self.session_id}.jsonl"

            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_record) + "\n")

            logger.info(f"Trace recorded for interaction {self.interaction_id} in {trace_file}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to record session trace for session {self.session_id}: {exc}")
