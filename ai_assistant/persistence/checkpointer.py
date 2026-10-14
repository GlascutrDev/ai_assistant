"""LangGraph checkpointer on MariaDB through frappe.db (SPEC §6.4). Writes join the caller's transaction."""

import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import frappe
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
	writes_sort_key,
)

from ai_assistant.persistence.dblock import LOCK


class FrappeCheckpointSaver(BaseCheckpointSaver[str]):
	def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
		"""See langgraph.checkpoint.base.BaseCheckpointSaver.get_tuple."""
		thread_id, ns = _thread(config)
		checkpoint_id = get_checkpoint_id(config)
		condition, values = "thread_id = %s and checkpoint_ns = %s", [thread_id, ns]
		if checkpoint_id:
			condition += " and checkpoint_id = %s"
			values.append(checkpoint_id)
		rows = _sql(
			f"select * from `ai_checkpoint` where {condition} order by checkpoint_id desc limit 1",
			values,
			as_dict=True,
		)
		return self._tuple(rows[0]) if rows else None

	def list(
		self,
		config: RunnableConfig | None,
		*,
		filter: dict[str, Any] | None = None,
		before: RunnableConfig | None = None,
		limit: int | None = None,
	) -> Iterator[CheckpointTuple]:
		"""See langgraph.checkpoint.base.BaseCheckpointSaver.list."""
		conditions, values = [], []
		if config:
			conditions.append("thread_id = %s")
			values.append(config["configurable"]["thread_id"])
			if config["configurable"].get("checkpoint_ns") is not None:
				conditions.append("checkpoint_ns = %s")
				values.append(config["configurable"]["checkpoint_ns"])
			if checkpoint_id := get_checkpoint_id(config):
				conditions.append("checkpoint_id = %s")
				values.append(checkpoint_id)
		if before and (before_id := get_checkpoint_id(before)):
			conditions.append("checkpoint_id < %s")
			values.append(before_id)
		where = f"where {' and '.join(conditions)}" if conditions else ""
		rows = _sql(
			f"select * from `ai_checkpoint` {where} order by checkpoint_id desc", values, as_dict=True
		)
		count = 0
		for row in rows:
			if limit is not None and count >= limit:
				return
			metadata = self._metadata(row)
			if filter and not all(metadata.get(k) == v for k, v in filter.items()):
				continue
			count += 1
			yield self._tuple(row, metadata)

	def put(
		self,
		config: RunnableConfig,
		checkpoint: Checkpoint,
		metadata: CheckpointMetadata,
		new_versions: ChannelVersions,
	) -> RunnableConfig:
		"""See langgraph.checkpoint.base.BaseCheckpointSaver.put."""
		thread_id, ns = _thread(config)
		copy = checkpoint.copy()
		channel_values = copy.pop("channel_values")
		for channel, version in new_versions.items():
			kind, blob = (
				self.serde.dumps_typed(channel_values[channel])
				if channel in channel_values
				else ("empty", None)
			)
			_sql(
				"""insert ignore into `ai_checkpoint_blob` (thread_id, checkpoint_ns, channel, version, type, `blob`)
				values (%s, %s, %s, %s, %s, unhex(%s))""",
				(thread_id, ns, channel, str(version), kind, _hex(blob)),
			)
		kind, blob = self.serde.dumps_typed(copy)
		meta_kind, meta_blob = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
		_sql(
			"""insert into `ai_checkpoint`
			(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata_type, metadata)
			values (%s, %s, %s, %s, %s, unhex(%s), %s, unhex(%s))
			on duplicate key update type = values(type), checkpoint = values(checkpoint),
				metadata_type = values(metadata_type), metadata = values(metadata)""",
			(
				thread_id,
				ns,
				checkpoint["id"],
				get_checkpoint_id(config),
				kind,
				_hex(blob),
				meta_kind,
				_hex(meta_blob),
			),
		)
		return {
			"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": checkpoint["id"]}
		}

	def put_writes(
		self,
		config: RunnableConfig,
		writes: Sequence[tuple[str, Any]],
		task_id: str,
		task_path: str = "",
	) -> None:
		"""See langgraph.checkpoint.base.BaseCheckpointSaver.put_writes."""
		thread_id, ns = _thread(config)
		checkpoint_id = config["configurable"]["checkpoint_id"]
		for idx, (channel, value) in enumerate(writes):
			write_idx = WRITES_IDX_MAP.get(channel, idx)
			kind, blob = self.serde.dumps_typed(value)
			verb = "replace" if write_idx < 0 else "insert ignore"
			_sql(
				f"""{verb} into `ai_checkpoint_write`
				(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, `blob`, task_path)
				values (%s, %s, %s, %s, %s, %s, %s, unhex(%s), %s)""",
				(thread_id, ns, checkpoint_id, task_id, write_idx, channel, kind, _hex(blob), task_path),
			)

	def delete_thread(self, thread_id: str) -> None:
		"""See langgraph.checkpoint.base.BaseCheckpointSaver.delete_thread."""
		for table in ("ai_checkpoint", "ai_checkpoint_blob", "ai_checkpoint_write"):
			_sql(f"delete from `{table}` where thread_id = %s", thread_id)

	async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
		"""See get_tuple."""
		return self.get_tuple(config)

	async def alist(
		self,
		config: RunnableConfig | None,
		*,
		filter: dict[str, Any] | None = None,
		before: RunnableConfig | None = None,
		limit: int | None = None,
	) -> AsyncIterator[CheckpointTuple]:
		"""See list."""
		for item in self.list(config, filter=filter, before=before, limit=limit):
			yield item

	async def aput(self, config, checkpoint, metadata, new_versions) -> RunnableConfig:
		"""See put."""
		return self.put(config, checkpoint, metadata, new_versions)

	async def aput_writes(self, config, writes, task_id, task_path: str = "") -> None:
		"""See put_writes."""
		return self.put_writes(config, writes, task_id, task_path)

	async def adelete_thread(self, thread_id: str) -> None:
		"""See delete_thread."""
		return self.delete_thread(thread_id)

	def get_next_version(self, current: str | None, channel: None) -> str:
		"""See langgraph.checkpoint.memory.InMemorySaver.get_next_version."""
		if current is None:
			current_v = 0
		elif isinstance(current, int):
			current_v = current
		else:
			current_v = int(current.split(".")[0])
		return f"{current_v + 1:032}.{random.random():016}"

	def _tuple(self, row: dict, metadata: dict | None = None) -> CheckpointTuple:
		thread_id, ns, checkpoint_id = row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"]
		checkpoint = self.serde.loads_typed((row["type"], bytes(row["checkpoint"])))
		checkpoint = {
			**checkpoint,
			"channel_values": self._blobs(thread_id, ns, checkpoint["channel_versions"]),
		}
		parent = row["parent_checkpoint_id"]
		return CheckpointTuple(
			config={
				"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": checkpoint_id}
			},
			checkpoint=checkpoint,
			metadata=metadata if metadata is not None else self._metadata(row),
			parent_config=(
				{"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": parent}}
				if parent
				else None
			),
			pending_writes=self._writes(thread_id, ns, checkpoint_id),
		)

	def _metadata(self, row: dict) -> dict:
		return self.serde.loads_typed((row["metadata_type"], bytes(row["metadata"])))

	def _blobs(self, thread_id: str, ns: str, versions: ChannelVersions) -> dict:
		if not versions:
			return {}
		pairs = [(channel, str(version)) for channel, version in versions.items()]
		placeholders = ", ".join(["(%s, %s)"] * len(pairs))
		rows = _sql(
			f"""select channel, type, `blob` from `ai_checkpoint_blob`
			where thread_id = %s and checkpoint_ns = %s and (channel, version) in ({placeholders})""",
			[thread_id, ns, *[v for pair in pairs for v in pair]],
			as_dict=True,
		)
		return {
			row["channel"]: self.serde.loads_typed((row["type"], bytes(row["blob"])))
			for row in rows
			if row["type"] != "empty"
		}

	def _writes(self, thread_id: str, ns: str, checkpoint_id: str) -> list:
		rows = _sql(
			"""select task_id, idx, channel, type, `blob`, task_path from `ai_checkpoint_write`
			where thread_id = %s and checkpoint_ns = %s and checkpoint_id = %s""",
			(thread_id, ns, checkpoint_id),
			as_dict=True,
		)
		rows.sort(key=lambda r: writes_sort_key(r["task_path"], r["task_id"], r["idx"]))
		return [
			(r["task_id"], r["channel"], self.serde.loads_typed((r["type"], bytes(r["blob"])))) for r in rows
		]


def _sql(*args, **kwargs):
	with LOCK:
		return frappe.db.sql(*args, **kwargs)


def _hex(blob: bytes | None) -> str | None:
	"""frappe.db.sql decodes the query as UTF-8, so binary values travel as hex and are unhexed in SQL."""
	return blob.hex() if blob is not None else None


def _thread(config: RunnableConfig) -> tuple[str, str]:
	return config["configurable"]["thread_id"], config["configurable"].get("checkpoint_ns", "")
