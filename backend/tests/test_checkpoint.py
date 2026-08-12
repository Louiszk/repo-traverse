import asyncio
from typing import cast
from unittest.mock import MagicMock

import fakeredis
import pytest
from app.checkpoint import RedisSaver
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata


def make_checkpoint(
    checkpoint_id: str,
    *,
    channel_values: dict | None = None,
    channel_versions: dict | None = None,
) -> Checkpoint:
    return cast(
        Checkpoint,
        {
            "v": 1,
            "id": checkpoint_id,
            "ts": "2026-07-31T00:00:00.000000+00:00",
            "channel_values": channel_values or {},
            "channel_versions": channel_versions or {},
            "versions_seen": {},
            "pending_sends": [],
        },
    )


def make_metadata(**extra: object) -> CheckpointMetadata:
    return cast(
        CheckpointMetadata,
        {
            "source": "input",
            "step": 1,
            "writes": {},
            "parents": {},
            **extra,
        },
    )


def test_redis_saver_put_and_get_round_trip():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(
        configurable={
            "thread_id": "session-1",
            "checkpoint_ns": "workflow:subgraph",
        }
    )

    checkpoint = make_checkpoint(
        "cp-1",
        channel_values={
            "state": {"repository": "fastapi", "files": ["app/main.py"]},
            "nullable": None,
        },
        channel_versions={
            "state": "1",
            "nullable": "1",
        },
    )
    versions = cast(ChannelVersions, {"state": "1", "nullable": "1"})

    result_config = saver.put(config, checkpoint, make_metadata(source="loop"), versions)

    result_cfg = result_config.get("configurable") or {}
    assert result_cfg.get("checkpoint_id") == "cp-1"

    restored = saver.get_tuple(result_config)

    assert restored is not None
    restored_cfg = restored.config.get("configurable") or {}
    assert restored_cfg.get("thread_id") == "session-1"
    assert restored_cfg.get("checkpoint_ns") == "workflow:subgraph"
    assert restored_cfg.get("checkpoint_id") == "cp-1"
    assert restored.metadata.get("source") == "loop"
    assert restored.checkpoint["channel_values"] == {
        "state": {"repository": "fastapi", "files": ["app/main.py"]},
        "nullable": None,
    }


def test_redis_saver_get_latest_skips_stale_index_entries():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""})

    saver.put(
        config,
        make_checkpoint(
            "valid-checkpoint",
            channel_values={"state": "available"},
            channel_versions={"state": "1"},
        ),
        make_metadata(),
        cast(ChannelVersions, {"state": "1"}),
    )

    index_key = saver._index_key("session-1", "")
    client.zadd(index_key, {"missing-checkpoint": 9_999_999_999})

    restored = saver.get_tuple(config)

    assert restored is not None
    restored_cfg = restored.config.get("configurable") or {}
    assert restored_cfg.get("checkpoint_id") == "valid-checkpoint"
    assert client.zscore(index_key, "missing-checkpoint") is None


def test_redis_saver_pending_writes_are_stably_ordered():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(
        configurable={
            "thread_id": "session-1",
            "checkpoint_ns": "",
            "checkpoint_id": "cp-1",
        }
    )

    saver.put(
        RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""}),
        make_checkpoint(
            "cp-1",
            channel_values={"state": "value"},
            channel_versions={"state": "1"},
        ),
        make_metadata(),
        cast(ChannelVersions, {"state": "1"}),
    )

    saver.put_writes(
        config,
        [("channel_a", "first"), ("channel_b", "second")],
        task_id="task-b",
        task_path="path-b",
    )
    saver.put_writes(
        config,
        [("channel_a", "third")],
        task_id="task-a",
        task_path="path-a",
    )

    restored = saver.get_tuple(config)

    assert restored is not None
    assert restored.pending_writes == [
        ("task-a", "channel_a", "third"),
        ("task-b", "channel_a", "first"),
        ("task-b", "channel_b", "second"),
    ]


def test_redis_saver_list_supports_namespace_colons_filters_and_limits():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    base_config = RunnableConfig(
        configurable={
            "thread_id": "thread:one",
            "checkpoint_ns": "parent:child",
        }
    )

    saver.put(
        base_config,
        make_checkpoint(
            "cp-1",
            channel_values={"state": "first"},
            channel_versions={"state": "1"},
        ),
        make_metadata(category="keep"),
        cast(ChannelVersions, {"state": "1"}),
    )
    saver.put(
        base_config,
        make_checkpoint(
            "cp-2",
            channel_values={"state": "second"},
            channel_versions={"state": "2"},
        ),
        make_metadata(category="keep"),
        cast(ChannelVersions, {"state": "2"}),
    )

    other_config = RunnableConfig(
        configurable={
            "thread_id": "thread:two",
            "checkpoint_ns": "other",
        }
    )
    saver.put(
        other_config,
        make_checkpoint(
            "cp-3",
            channel_values={"state": "ignored"},
            channel_versions={"state": "1"},
        ),
        make_metadata(category="discard"),
        cast(ChannelVersions, {"state": "1"}),
    )

    results = list(saver.list(None, filter={"category": "keep"}, limit=1))

    assert len(results) == 1
    assert results[0].metadata.get("category") == "keep"
    res_cfg = results[0].config.get("configurable") or {}
    assert res_cfg.get("thread_id") == "thread:one"
    assert res_cfg.get("checkpoint_ns") == "parent:child"


def test_redis_saver_delete_thread_removes_all_thread_keys():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""})

    saver.put(
        config,
        make_checkpoint(
            "cp-1",
            channel_values={"state": "value"},
            channel_versions={"state": "1"},
        ),
        make_metadata(),
        cast(ChannelVersions, {"state": "1"}),
    )
    saver.put_writes(
        RunnableConfig(
            configurable={
                "thread_id": "session-1",
                "checkpoint_ns": "",
                "checkpoint_id": "cp-1",
            }
        ),
        [("channel", "pending")],
        task_id="task-1",
    )

    saver.delete_thread("session-1")

    assert saver.get_tuple(config) is None
    assert list(client.scan_iter(match="checkpoint:*")) == []
    assert list(client.scan_iter(match="checkpoint_blobs:*")) == []
    assert list(client.scan_iter(match="checkpoint_writes:*")) == []
    assert list(client.scan_iter(match="checkpoint_index:*")) == []


def test_redis_saver_async_methods_do_not_require_an_async_redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(configurable={"thread_id": "session-async", "checkpoint_ns": ""})

    async def run_test() -> None:
        await saver.aput(
            config,
            make_checkpoint(
                "cp-async",
                channel_values={"state": "async-value"},
                channel_versions={"state": "1"},
            ),
            make_metadata(),
            cast(ChannelVersions, {"state": "1"}),
        )

        restored = await saver.aget_tuple(config)
        assert restored is not None
        assert restored.checkpoint["channel_values"]["state"] == "async-value"

        listed = [
            item
            async for item in saver.alist(
                RunnableConfig(configurable={"thread_id": "session-async", "checkpoint_ns": ""})
            )
        ]
        assert len(listed) == 1

        await saver.adelete_thread("session-async")
        assert await saver.aget_tuple(config) is None

    asyncio.run(run_test())


def test_redis_saver_rejects_invalid_ttl():
    with pytest.raises(ValueError, match="ttl_seconds"):
        RedisSaver(redis_client=fakeredis.FakeRedis(decode_responses=True), ttl_seconds=0)


def test_redis_saver_put_uses_atomic_pipeline():
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    saver = RedisSaver(redis_client=mock_redis, ttl_seconds=3600)
    config = RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""})

    saver.put(
        config,
        make_checkpoint(
            "cp-1",
            channel_values={},
            channel_versions={},
        ),
        make_metadata(),
        cast(ChannelVersions, {"channel": "v1"}),
    )

    mock_redis.pipeline.assert_called_once_with(transaction=True)
    assert mock_pipe.hset.called
    assert mock_pipe.setex.called
    assert mock_pipe.zadd.called
    assert mock_pipe.expire.called
    mock_pipe.execute.assert_called_once()


def test_redis_saver_refreshes_ttl_on_read():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""})

    saver.put(
        config,
        make_checkpoint(
            "cp-1",
            channel_values={"state": "v1"},
            channel_versions={"state": "1"},
        ),
        make_metadata(),
        cast(ChannelVersions, {"state": "1"}),
    )

    # Read checkpoint and verify TTL is refreshed
    restored = saver.get_tuple(config)
    assert restored is not None

    cp_key = saver._checkpoint_key("session-1", "", "cp-1")
    ttl = cast(int, client.ttl(cp_key))
    assert ttl > 0


def test_redis_saver_stringifies_channel_versions():
    client = fakeredis.FakeRedis(decode_responses=True)
    saver = RedisSaver(redis_client=client, ttl_seconds=3600)

    config = RunnableConfig(configurable={"thread_id": "session-1", "checkpoint_ns": ""})

    # Pass integer version in channel_versions
    raw_checkpoint = make_checkpoint(
        "cp-int-version",
        channel_values={"state": "v1"},
        channel_versions={"state": 123},  # integer version (LangGraph issue #40 scenario)
    )

    saver.put(
        config,
        raw_checkpoint,
        make_metadata(),
        cast(ChannelVersions, {"state": 123}),
    )

    restored = saver.get_tuple(config)
    assert restored is not None
    assert restored.checkpoint["channel_versions"]["state"] == "123"


def test_redis_saver_get_next_version():
    saver = RedisSaver(redis_client=fakeredis.FakeRedis(decode_responses=True))

    v1 = saver.get_next_version(None)
    assert isinstance(v1, str)
    assert v1.startswith("00000000000000000000000000000001.")

    v2 = saver.get_next_version(v1)
    assert isinstance(v2, str)
    assert v2.startswith("00000000000000000000000000000002.")

    v_int = saver.get_next_version(5)
    assert isinstance(v_int, str)
    assert v_int.startswith("00000000000000000000000000000006.")
