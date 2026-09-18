# Custom Redis Checkpoint Saver for LangGraph.
# We intentionally use this custom `RedisSaver` instead of the official `langgraph-checkpoint-redis` package.
# The official `langgraph-checkpoint-redis` requires Redis 8+ or Redis Stack

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast
from urllib.parse import quote, unquote

import redis
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.serde.base import SerializerProtocol

from app.config import settings
from app.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_DELETE_BATCH_SIZE = 500
_ASYNC_ITERATION_DONE = object()


class RedisSaver(BaseCheckpointSaver[str]):
    """
    Distributed LangGraph checkpoint saver backed by Redis.

    Checkpoint payloads, channel blobs, pending writes, and per-thread indexes are
    stored separately so unchanged channel values are not duplicated in every
    checkpoint record.
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        *,
        ttl_seconds: int | None = None,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde)

        configured_ttl = ttl_seconds if ttl_seconds is not None else settings.repo_max_age_seconds
        if configured_ttl <= 0:
            raise ValueError("ttl_seconds must be greater than zero.")

        self._redis_client = redis_client
        self.ttl_seconds = int(configured_ttl)

    @property
    def client(self) -> redis.Redis:
        """Lazily initializes the Redis client to keep construction test-friendly."""
        if self._redis_client is None:
            self._redis_client = get_redis_client()
        return self._redis_client

    def get_next_version(self, current: str | float | None, channel: Any = None) -> str:
        """Generates monotonically increasing channel version strings."""
        if current is None:
            current_v = 0
        elif isinstance(current, (int, float)):
            current_v = int(current)
        else:
            try:
                current_v = int(str(current).split(".")[0])
            except (ValueError, AttributeError):
                current_v = 0
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    @staticmethod
    def _to_text(value: str | bytes | Any) -> str:
        """Converts Redis string/bytes responses into text."""
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @staticmethod
    def _encode_key_part(value: str) -> str:
        """
        Encodes key components safely.

        LangGraph checkpoint namespaces can contain ':' characters. Encoding each
        component avoids ambiguous Redis key parsing during global list/delete
        operations and prevents glob-pattern injection through identifiers.
        """
        return quote(value, safe="")

    @staticmethod
    def _decode_key_part(value: str) -> str:
        return unquote(value)

    def _checkpoint_key(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        return (
            f"checkpoint:{self._encode_key_part(thread_id)}:"
            f"{self._encode_key_part(checkpoint_ns)}:{self._encode_key_part(checkpoint_id)}"
        )

    def _index_key(self, thread_id: str, checkpoint_ns: str) -> str:
        return f"checkpoint_index:{self._encode_key_part(thread_id)}:{self._encode_key_part(checkpoint_ns)}"

    def _blob_key(self, thread_id: str, checkpoint_ns: str) -> str:
        return f"checkpoint_blobs:{self._encode_key_part(thread_id)}:{self._encode_key_part(checkpoint_ns)}"

    def _writes_key(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        return (
            f"checkpoint_writes:{self._encode_key_part(thread_id)}:"
            f"{self._encode_key_part(checkpoint_ns)}:{self._encode_key_part(checkpoint_id)}"
        )

    def _dump_typed(self, value: Any) -> str:
        """Serializes a value using LangGraph's configured typed serializer."""
        type_name, payload = self.serde.dumps_typed(value)
        return f"{type_name}:{payload.hex()}"

    def _load_typed(self, raw: str | bytes | None) -> Any:
        """
        Deserializes a typed value.

        ``empty:`` is the sentinel used for a channel that has no stored value.
        A serialized Python ``None`` remains distinct from this sentinel.
        """
        if raw is None:
            return None

        raw_text = self._to_text(raw)
        if raw_text == "empty:":
            return None

        type_name, separator, hex_payload = raw_text.partition(":")
        if not separator:
            logger.warning("Ignoring malformed Redis checkpoint value.")
            return None

        try:
            return self.serde.loads_typed((type_name, bytes.fromhex(hex_payload)))
        except (TypeError, ValueError, UnicodeError) as exc:
            logger.warning("Unable to deserialize Redis checkpoint value: %s", exc)
            return None

    def _load_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        versions: ChannelVersions,
    ) -> dict[str, Any]:
        """Loads all channel blobs for a checkpoint in one HMGET round trip."""
        if not versions:
            return {}

        fields = [f"{channel}:{version}" for channel, version in versions.items()]
        raw_values = cast(list[Any], self.client.hmget(self._blob_key(thread_id, checkpoint_ns), fields))

        channel_values: dict[str, Any] = {}
        for (channel, _version), raw_value in zip(versions.items(), raw_values):
            if raw_value is None:
                continue

            # Preserve an explicitly serialized None. Only the explicit empty
            # sentinel means the channel should be absent from channel_values.
            if self._to_text(raw_value) == "empty:":
                continue

            channel_values[channel] = self._load_typed(raw_value)

        return channel_values

    def _load_pending_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[tuple[str, str, Any]]:
        """
        Loads pending writes in deterministic task-path/task/index order.

        Redis hashes do not preserve insertion order. LangGraph relies on stable
        pending-write ordering when recovering interrupted graph executions.
        """
        writes_key = self._writes_key(thread_id, checkpoint_ns, checkpoint_id)
        raw_writes = cast(dict[Any, Any], self.client.hgetall(writes_key))

        ordered_writes: list[tuple[str, str, int, str, Any]] = []

        for fallback_index, (field, raw_value) in enumerate(raw_writes.items()):
            try:
                write_data = json.loads(self._to_text(raw_value))
                task_id = str(write_data[0])
                channel = str(write_data[1])
                dumped_value = write_data[2]
                task_path = str(write_data[3]) if len(write_data) > 3 else ""
            except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Ignoring malformed pending write for checkpoint %s: %s", checkpoint_id, exc)
                continue

            field_text = self._to_text(field)
            try:
                write_index = int(field_text.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                write_index = fallback_index

            ordered_writes.append(
                (
                    task_path,
                    task_id,
                    write_index,
                    channel,
                    self._load_typed(dumped_value),
                )
            )

        ordered_writes.sort(key=lambda item: (item[0], item[1], item[2]))
        return [(task_id, channel, value) for _path, task_id, _index, channel, value in ordered_writes]

    def _build_tuple(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> CheckpointTuple | None:
        """Loads and reconstructs one complete checkpoint tuple."""
        checkpoint_key = self._checkpoint_key(thread_id, checkpoint_ns, checkpoint_id)
        saved_raw = cast(str | bytes | None, self.client.get(checkpoint_key))

        if saved_raw is None:
            return None

        try:
            record = json.loads(self._to_text(saved_raw))
            checkpoint_dumped, metadata_dumped, parent_checkpoint_id = record
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring malformed checkpoint record %s: %s", checkpoint_id, exc)
            return None

        checkpoint = self._load_typed(checkpoint_dumped)
        metadata = self._load_typed(metadata_dumped)

        if not isinstance(checkpoint, dict) or not isinstance(metadata, dict):
            logger.warning("Ignoring invalid checkpoint payload for checkpoint %s.", checkpoint_id)
            return None

        channel_versions = checkpoint.get("channel_versions")
        if not isinstance(channel_versions, dict):
            logger.warning("Ignoring checkpoint %s with invalid channel_versions.", checkpoint_id)
            return None

        parent_config: RunnableConfig | None = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": str(parent_checkpoint_id),
                }
            }

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint={
                **cast(Checkpoint, checkpoint),
                "channel_values": self._load_blobs(
                    thread_id,
                    checkpoint_ns,
                    cast(ChannelVersions, channel_versions),
                ),
            },
            metadata=cast(CheckpointMetadata, metadata),
            pending_writes=self._load_pending_writes(thread_id, checkpoint_ns, checkpoint_id),
            parent_config=parent_config,
        )

    def _refresh_ttl(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> None:
        """Best-effort TTL refresh on read to keep active sessions alive."""
        try:
            pipe = self.client.pipeline(transaction=False)
            pipe.expire(self._checkpoint_key(thread_id, checkpoint_ns, checkpoint_id), self.ttl_seconds)
            pipe.expire(self._blob_key(thread_id, checkpoint_ns), self.ttl_seconds)
            pipe.expire(self._index_key(thread_id, checkpoint_ns), self.ttl_seconds)
            pipe.expire(self._writes_key(thread_id, checkpoint_ns, checkpoint_id), self.ttl_seconds)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to refresh TTL on read for checkpoint %s: %s", checkpoint_id, exc)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Returns the requested checkpoint, or the latest one in its namespace."""
        configurable = config.get("configurable") or {}
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)

        index_key = self._index_key(thread_id, checkpoint_ns)

        if checkpoint_id:
            result = self._build_tuple(thread_id, checkpoint_ns, str(checkpoint_id))
            if result is None:
                # A checkpoint payload can expire or be manually removed before
                # its index entry. Remove the stale index member opportunistically.
                self.client.zrem(index_key, str(checkpoint_id))
            else:
                self._refresh_ttl(thread_id, checkpoint_ns, str(checkpoint_id))
            return result

        checkpoint_ids = cast(list[Any], self.client.zrevrange(index_key, 0, -1))
        for raw_checkpoint_id in checkpoint_ids:
            latest_id = self._to_text(raw_checkpoint_id)
            result = self._build_tuple(thread_id, checkpoint_ns, latest_id)
            if result is not None:
                self._refresh_ttl(thread_id, checkpoint_ns, latest_id)
                return result

            # Do not let a stale newest index member hide an older valid checkpoint.
            self.client.zrem(index_key, latest_id)

        return None

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Persists a checkpoint and its newly-versioned channel blobs atomically."""
        configurable = config.get("configurable") or {}
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])

        checkpoint_data = checkpoint.copy()
        if "channel_versions" in checkpoint_data and isinstance(checkpoint_data["channel_versions"], dict):
            checkpoint_data["channel_versions"] = {
                str(k): str(v) for k, v in checkpoint_data["channel_versions"].items()
            }

        channel_values = cast(dict[str, Any], checkpoint_data.pop("channel_values", {}))

        blob_mapping: dict[str, str] = {}
        for channel, version in new_versions.items():
            field = f"{channel}:{version}"
            blob_mapping[field] = self._dump_typed(channel_values[channel]) if channel in channel_values else "empty:"

        parent_checkpoint_id = get_checkpoint_id(config)
        serialized_checkpoint = [
            self._dump_typed(checkpoint_data),
            self._dump_typed(get_checkpoint_metadata(config, metadata)),
            str(parent_checkpoint_id) if parent_checkpoint_id else None,
        ]

        blob_key = self._blob_key(thread_id, checkpoint_ns)
        checkpoint_key = self._checkpoint_key(thread_id, checkpoint_ns, checkpoint_id)
        index_key = self._index_key(thread_id, checkpoint_ns)

        # redis-py's normal pipeline is transactional by default. Keeping all
        # writes in one execution avoids persisting an index entry before its
        # corresponding checkpoint payload is available.
        pipe = self.client.pipeline(transaction=True)

        if blob_mapping:
            pipe.hset(blob_key, mapping=blob_mapping)

        # Refreshing the blob hash retains historical versioned values while the
        # session is active, preventing a checkpoint from referencing expired blobs.
        pipe.expire(blob_key, self.ttl_seconds)
        pipe.setex(
            checkpoint_key,
            self.ttl_seconds,
            json.dumps(serialized_checkpoint, separators=(",", ":")),
        )
        pipe.zadd(index_key, {checkpoint_id: time.time()})
        pipe.expire(index_key, self.ttl_seconds)
        pipe.execute()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persists pending writes for a graph task atomically."""
        if not writes:
            return

        configurable = config.get("configurable") or {}
        thread_id = str(configurable.get("thread_id", ""))
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable.get("checkpoint_id", ""))

        writes_key = self._writes_key(thread_id, checkpoint_ns, checkpoint_id)
        pipe = self.client.pipeline(transaction=True)

        for write_position, (channel, value) in enumerate(writes):
            write_index = WRITES_IDX_MAP.get(channel, write_position)
            field_name = f"{task_id}:{write_index}"
            write_record = [
                task_id,
                channel,
                self._dump_typed(value),
                task_path,
            ]
            pipe.hset(writes_key, field_name, json.dumps(write_record, separators=(",", ":")))

        pipe.expire(writes_key, self.ttl_seconds)
        pipe.execute()

    def _index_entries(
        self,
        config: RunnableConfig | None,
    ) -> list[tuple[str, str, str]]:
        """
        Returns (thread_id, namespace, Redis-index-key) entries in the requested scope.
        """
        if config is not None:
            configurable = config.get("configurable") or {}
            thread_id = str(configurable.get("thread_id", ""))

            if "checkpoint_ns" in configurable:
                checkpoint_ns = str(configurable["checkpoint_ns"])
                return [(thread_id, checkpoint_ns, self._index_key(thread_id, checkpoint_ns))]

            pattern = f"checkpoint_index:{self._encode_key_part(thread_id)}:*"
        else:
            pattern = "checkpoint_index:*"

        entries: list[tuple[str, str, str]] = []
        for raw_key in self.client.scan_iter(match=pattern):
            key = self._to_text(raw_key)
            parts = key.split(":", 2)
            if len(parts) != 3:
                continue

            try:
                thread_id = self._decode_key_part(parts[1])
                checkpoint_ns = self._decode_key_part(parts[2])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ignoring malformed Redis checkpoint index key %r: %s", key, exc)
                continue

            entries.append((thread_id, checkpoint_ns, key))

        return entries

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """
        Lists checkpoints newest-first.

        Unlike Redis SCAN order, returned results are ordered by their ZSET
        timestamp globally across all selected checkpoint namespaces.
        """
        if limit is not None and limit <= 0:
            return

        config_checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        candidates: list[tuple[float, str, str, str]] = []

        for thread_id, checkpoint_ns, index_key in self._index_entries(config):
            before_score: float | None = None
            if before_checkpoint_id:
                raw_score = cast(str | bytes | float | None, self.client.zscore(index_key, str(before_checkpoint_id)))
                before_score = float(raw_score) if raw_score is not None else None

            entries = cast(
                list[tuple[Any, float]],
                self.client.zrevrange(index_key, 0, -1, withscores=True),
            )

            for raw_checkpoint_id, score in entries:
                checkpoint_id = self._to_text(raw_checkpoint_id)

                if config_checkpoint_id and checkpoint_id != str(config_checkpoint_id):
                    continue

                if before_checkpoint_id:
                    if before_score is not None:
                        if float(score) >= before_score:
                            continue
                    elif checkpoint_id >= str(before_checkpoint_id):
                        # Fallback for a `before` checkpoint that is no longer
                        # present in this namespace's index.
                        continue

                candidates.append((float(score), thread_id, checkpoint_ns, checkpoint_id))

        # Timestamp is the primary ordering. Checkpoint ID makes equal-score
        # ordering deterministic, which is useful in tests and concurrent writes.
        candidates.sort(key=lambda item: (item[0], item[3]), reverse=True)

        yielded = 0
        for _score, thread_id, checkpoint_ns, checkpoint_id in candidates:
            checkpoint_tuple = self.get_tuple(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                }
            )
            if checkpoint_tuple is None:
                continue

            if filter and not all(
                checkpoint_tuple.metadata.get(field_name) == expected_value
                for field_name, expected_value in filter.items()
            ):
                continue

            yield checkpoint_tuple
            yielded += 1

            if limit is not None and yielded >= limit:
                return

    def delete_thread(self, thread_id: str) -> None:
        """Deletes every checkpoint-related Redis key for one LangGraph thread."""
        encoded_thread_id = self._encode_key_part(thread_id)
        patterns = (
            f"checkpoint:{encoded_thread_id}:*",
            f"checkpoint_writes:{encoded_thread_id}:*",
            f"checkpoint_blobs:{encoded_thread_id}:*",
            f"checkpoint_index:{encoded_thread_id}:*",
        )

        pending_keys: list[Any] = []
        for pattern in patterns:
            for key in self.client.scan_iter(match=pattern):
                pending_keys.append(key)

                if len(pending_keys) >= _DELETE_BATCH_SIZE:
                    self.client.delete(*pending_keys)
                    pending_keys.clear()

        if pending_keys:
            self.client.delete(*pending_keys)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """
        Streams synchronous list results without blocking the event loop or
        materializing the complete checkpoint history in memory.
        """
        iterator = self.list(config, filter=filter, before=before, limit=limit)

        def next_item() -> CheckpointTuple | object:
            try:
                return next(iterator)
            except StopIteration:
                return _ASYNC_ITERATION_DONE

        while True:
            item = await asyncio.to_thread(next_item)
            if item is _ASYNC_ITERATION_DONE:
                break
            yield cast(CheckpointTuple, item)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)
