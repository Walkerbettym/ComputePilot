"""Task-level cache: check input hash + command hash to skip already-run tasks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sciflow.models.workflow import Task


@dataclass
class CacheKey:
    """Unique key for a task execution: command + input checksums + env."""

    task_id: str
    command_hash: str
    input_checksums: dict[str, str] = field(default_factory=dict)
    env_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "command_hash": self.command_hash,
            "input_checksums": self.input_checksums,
            "env_hash": self.env_hash,
        }

    @classmethod
    def from_task(cls, task: Task, input_checksums: dict[str, str] | None = None) -> CacheKey:
        """Build a CacheKey from a Task and optional input file checksums."""
        command_hash = hashlib.sha256(
            json.dumps(
                {"command": task.command, "args": task.args, "type": task.type.value},
                sort_keys=True,
            ).encode()
        ).hexdigest()

        env_hash = ""
        if task.environment:
            env_hash = hashlib.sha256(
                json.dumps(task.environment, sort_keys=True).encode()
            ).hexdigest()

        return cls(
            task_id=task.id,
            command_hash=command_hash,
            input_checksums=input_checksums or {},
            env_hash=env_hash,
        )


@dataclass
class CacheEntry:
    """A cached result for a task execution."""

    key: CacheKey
    output_checksums: dict[str, str] = field(default_factory=dict)
    exit_code: int | None = None

    def matches(self, other: CacheKey) -> bool:
        """Return True if *other* key matches this entry (same cmd + inputs + env)."""
        return (
            self.key.command_hash == other.command_hash
            and self.key.input_checksums == other.input_checksums
            and self.key.env_hash == other.env_hash
        )


class TaskCache:
    """Persistent task cache backed by a JSON file.

    The cache maps command+input+env hashes to output checksums,
    allowing the scheduler to skip tasks whose inputs haven't changed.
    """

    def __init__(self, cache_path: str | Path = ".sciflow_cache.json") -> None:
        self._path = Path(cache_path)
        self._entries: list[CacheEntry] = []
        self._load()

    def get(self, key: CacheKey) -> CacheEntry | None:
        """Return a matching cache entry, or None if no match."""
        for entry in self._entries:
            if entry.matches(key):
                return entry
        return None

    def put(self, entry: CacheEntry) -> None:
        """Store a cache entry."""
        # Replace existing entry with the same key (task_id + command_hash)
        for i, existing in enumerate(self._entries):
            if (
                existing.key.task_id == entry.key.task_id
                and existing.key.command_hash == entry.key.command_hash
            ):
                self._entries[i] = entry
                self._save()
                return
        self._entries.append(entry)
        self._save()

    def clear(self) -> None:
        """Clear all cache entries."""
        self._entries.clear()
        self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self._entries = [
                CacheEntry(
                    key=CacheKey(**e["key"]),
                    output_checksums=e.get("output_checksums", {}),
                    exit_code=e.get("exit_code"),
                )
                for e in data
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._entries = []

    def _save(self) -> None:
        data = [
            {
                "key": entry.key.to_dict(),
                "output_checksums": entry.output_checksums,
                "exit_code": entry.exit_code,
            }
            for entry in self._entries
        ]
        self._path.write_text(json.dumps(data, indent=2))
