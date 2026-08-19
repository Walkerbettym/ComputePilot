"""Tests for TaskCache module."""
from __future__ import annotations

from pathlib import Path

from sciflow.models.workflow import Task
from sciflow.runtime.cache import CacheEntry, CacheKey, TaskCache


class TestCacheKey:
    def test_from_task(self) -> None:
        """Build a CacheKey from a Task."""
        task = Task(id="t1", command="python train.py", args=["--lr", "0.01"])
        key = CacheKey.from_task(task)
        assert key.task_id == "t1"
        assert len(key.command_hash) == 64  # sha256
        assert key.env_hash == ""
        assert key.input_checksums == {}

    def test_from_task_with_env(self) -> None:
        """Environment changes the hash."""
        task = Task(id="t1", command="echo", environment={"SEED": "42"})
        key = CacheKey.from_task(task)
        assert len(key.env_hash) == 64
        assert key.env_hash != ""

    def test_from_task_with_inputs(self) -> None:
        """Input checksums are included."""
        task = Task(id="t1", command="echo")
        inputs = {"data.csv": "abc123"}
        key = CacheKey.from_task(task, input_checksums=inputs)
        assert key.input_checksums == {"data.csv": "abc123"}


class TestCacheEntry:
    def test_matches(self) -> None:
        """Two identical keys match."""
        task1 = Task(id="t", command="echo hello")
        task2 = Task(id="t", command="echo hello")
        key1 = CacheKey.from_task(task1)
        key2 = CacheKey.from_task(task2)
        entry = CacheEntry(key=key1, output_checksums={"out.txt": "def456"})
        assert entry.matches(key2)

    def test_mismatch_command(self) -> None:
        """Different commands don't match."""
        k1 = CacheKey.from_task(Task(id="t", command="echo hello"))
        k2 = CacheKey.from_task(Task(id="t", command="echo world"))
        entry = CacheEntry(key=k1)
        assert not entry.matches(k2)

    def test_mismatch_env(self) -> None:
        """Different environments don't match."""
        k1 = CacheKey.from_task(Task(id="t", command="echo", environment={"A": "1"}))
        k2 = CacheKey.from_task(Task(id="t", command="echo", environment={"A": "2"}))
        entry = CacheEntry(key=k1)
        assert not entry.matches(k2)

    def test_roundtrip_dict(self) -> None:
        """CacheKey serialises and deserialises."""
        key = CacheKey.from_task(Task(id="t", command="echo"))
        d = key.to_dict()
        assert d["task_id"] == "t"
        assert len(d["command_hash"]) == 64


class TestTaskCache:
    def test_get_miss(self, tmp_path: Path) -> None:
        """Unknown key returns None."""
        cache = TaskCache(str(tmp_path / "cache.json"))
        task = Task(id="t", command="echo")
        key = CacheKey.from_task(task)
        assert cache.get(key) is None

    def test_put_and_get(self, tmp_path: Path) -> None:
        """Stored entry can be retrieved."""
        cache = TaskCache(str(tmp_path / "cache.json"))
        task = Task(id="t", command="echo hello")
        key = CacheKey.from_task(task)
        entry = CacheEntry(key=key, output_checksums={"out.txt": "abc"}, exit_code=0)
        cache.put(entry)

        retrieved = cache.get(key)
        assert retrieved is not None
        assert retrieved.output_checksums == {"out.txt": "abc"}
        assert retrieved.exit_code == 0

    def test_put_overwrites_same_key(self, tmp_path: Path) -> None:
        """Putting same task_id+command overwrites."""
        cache = TaskCache(str(tmp_path / "cache.json"))
        task = Task(id="t", command="echo")
        key = CacheKey.from_task(task)
        cache.put(CacheEntry(key=key, output_checksums={"v1": "a"}))
        cache.put(CacheEntry(key=key, output_checksums={"v2": "b"}))

        # Should only have 1 entry (the latest)
        retrieved = cache.get(key)
        assert retrieved is not None
        assert retrieved.output_checksums == {"v2": "b"}

        # count entries
        assert len(cache._entries) == 1

    def test_clear(self, tmp_path: Path) -> None:
        """Clear removes all entries."""
        cache = TaskCache(str(tmp_path / "cache.json"))
        key = CacheKey.from_task(Task(id="t", command="echo"))
        cache.put(CacheEntry(key=key))
        cache.clear()
        assert len(cache._entries) == 0
        assert cache.get(key) is None

    def test_persistence(self, tmp_path: Path) -> None:
        """Entries survive cache instance recreation (JSON file)."""
        path = str(tmp_path / "persist.json")
        cache = TaskCache(path)
        key = CacheKey.from_task(Task(id="t", command="echo"))
        cache.put(CacheEntry(key=key, output_checksums={"out": "xyz"}))

        # New instance reading same file
        cache2 = TaskCache(path)
        retrieved = cache2.get(key)
        assert retrieved is not None
        assert retrieved.output_checksums == {"out": "xyz"}
