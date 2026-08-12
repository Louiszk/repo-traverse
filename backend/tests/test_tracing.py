import json
import time
from pathlib import Path
from unittest.mock import patch

from app.cleanup import cleanup_traces
from app.tracing import SessionTracer, calculate_token_cost, sanitize_trace_args


def test_sanitize_trace_args():
    """Test that sanitize_trace_args truncates long strings and strips internal params."""
    long_string = "a" * 300
    args = {
        "query": "test",
        "session_id": "secret_id",
        "code": long_string,
        "nested": {"nested_code": "b" * 250},
        "list_val": ["normal", "c" * 220],
    }

    sanitized = sanitize_trace_args(args, max_str_len=200)

    assert "session_id" not in sanitized
    assert sanitized["query"] == "test"
    assert len(sanitized["code"]) == 203  # 200 + '...'
    assert sanitized["code"].endswith("...")
    assert len(sanitized["nested"]["nested_code"]) == 203
    assert sanitized["list_val"][0] == "normal"
    assert len(sanitized["list_val"][1]) == 203


@patch("app.tracing.settings.cost_input_tokens", 0.20)
@patch("app.tracing.settings.cost_cached_input_tokens", 0.02)
@patch("app.tracing.settings.cost_output_tokens", 1.25)
def test_calculate_token_cost():
    """Test pricing calculation."""
    # input: 1M, cached: 0.5M -> 0.5M standard @ 0.20 + 0.5M cached @ 0.02 = 0.10 + 0.01 = 0.11
    # output: 1M @ 1.25 = 1.25 -> Total = 1.36
    cost = calculate_token_cost(1_000_000, 500_000, 1_000_000)
    assert abs(cost - 1.36) < 1e-6


@patch("app.tracing.record_token_usage")
def test_session_tracer_lifecycle(mock_record_usage, tmp_path: Path):
    """Test full SessionTracer turn tracking and JSONL output structure."""
    with patch("app.tracing.settings.shared_data_dir", str(tmp_path)):
        session_id = "test-session-123"
        user_message = "Hello, analyze repo!"

        tracer = SessionTracer(session_id, user_message)

        # Turn 1
        tracer.start_turn()
        tracer.record_ttft()
        time.sleep(0.01)

        tracer.start_tool("search_graph", {"query": "auth", "session_id": "internal"})
        time.sleep(0.01)
        tracer.end_tool("search_graph", status="success")

        usage_1 = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_token_details": {"cache_read": 800},
        }
        tracer.end_llm_turn(usage_1)

        # Turn 2
        tracer.start_turn()
        usage_2 = {
            "input_tokens": 2000,
            "output_tokens": 300,
            "input_token_details": {"cache_read": 1000},
        }
        tracer.end_llm_turn(usage_2)

        tracer.finalize("Analysis completed successfully.")

        trace_file = tmp_path / "traces" / f"{session_id}.jsonl"
        assert trace_file.exists()

        lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

        record = json.loads(lines[0])

        assert record["interaction_id"].startswith("req_")
        assert record["meta"]["user_message_length_chars"] == len(user_message)
        assert record["meta"]["final_reply_length_chars"] == len("Analysis completed successfully.")

        assert record["overall_metrics"]["total_tokens"]["input"] == 3000
        assert record["overall_metrics"]["total_tokens"]["cached_input"] == 1800
        assert record["overall_metrics"]["total_tokens"]["output"] == 500
        assert record["overall_metrics"]["overall_cache_hit_rate"] == round(1800 / 3000, 4)

        assert len(record["turns"]) == 2
        turn1 = record["turns"][0]
        assert turn1["turn_index"] == 1
        assert turn1["tokens"]["input"] == 1000
        assert turn1["tokens"]["cached_input"] == 800
        assert turn1["tokens"]["output"] == 200
        assert turn1["cache_hit_rate"] == 0.8
        assert len(turn1["tools"]) == 1
        assert turn1["tools"][0]["name"] == "search_graph"
        assert "session_id" not in turn1["tools"][0]["args"]

        mock_record_usage.assert_called()


def test_cleanup_traces_fifo(tmp_path: Path):
    """Test FIFO eviction of trace files when total storage exceeds threshold."""
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    t1 = traces_dir / "sess_1.jsonl"
    t2 = traces_dir / "sess_2.jsonl"
    t3 = traces_dir / "sess_3.jsonl"

    t1.write_bytes(b"X" * 100)
    t2.write_bytes(b"Y" * 100)
    t3.write_bytes(b"Z" * 100)

    now = time.time()
    import os

    os.utime(t1, (now - 300, now - 300))
    os.utime(t2, (now - 200, now - 200))
    os.utime(t3, (now - 100, now - 100))

    # Threshold = 200 bytes (~1.86e-7 GB). Target (90%) = 180 bytes.
    threshold_gb = 200 / (1024 * 1024 * 1024)

    with (
        patch("app.cleanup.settings.shared_data_dir", str(tmp_path)),
        patch("app.cleanup.settings.traces_max_age_seconds", 60 * 24 * 60 * 60),
        patch("app.cleanup.settings.traces_storage_threshold_gb", threshold_gb),
    ):
        res = cleanup_traces()

        # To drop beneath 90% of threshold (180 bytes), oldest traces t1 and t2 (200 bytes deleted) are evicted FIFO
        assert "sess_1.jsonl" in res["deleted_traces"]
        assert "sess_2.jsonl" in res["deleted_traces"]
        assert "sess_3.jsonl" not in res["deleted_traces"]
        assert not t1.exists()
        assert not t2.exists()
        assert t3.exists()


def test_cleanup_traces_expired_by_age(tmp_path: Path):
    """Test that traces older than the max age are deleted even when storage is below threshold."""
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    old_trace = traces_dir / "old.jsonl"
    new_trace = traces_dir / "new.jsonl"

    old_trace.write_bytes(b"X" * 100)
    new_trace.write_bytes(b"Y" * 100)

    now = time.time()
    import os

    sixty_days_seconds = 60 * 24 * 60 * 60
    os.utime(old_trace, (now - sixty_days_seconds - 10, now - sixty_days_seconds - 10))
    os.utime(new_trace, (now - 100, now - 100))

    with (
        patch("app.cleanup.settings.shared_data_dir", str(tmp_path)),
        patch("app.cleanup.settings.traces_max_age_seconds", sixty_days_seconds),
        patch("app.cleanup.settings.traces_storage_threshold_gb", 10.0),
    ):
        res = cleanup_traces()

        assert res["deleted_traces"] == ["old.jsonl"]
        assert not old_trace.exists()
        assert new_trace.exists()
