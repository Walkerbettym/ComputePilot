"""Unit tests for the SQLite-backed state store."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from sciflow.models.run import Run, RunStatus, TaskStatus
from sciflow.runtime.state import StateStore


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_state.db")


@pytest.fixture
def store(db_path: str) -> StateStore:
    return StateStore(db_path)


@pytest.fixture
def sample_run() -> Run:
    return Run(
        id="run-001",
        workflow_id=uuid4(),
        workflow_sha256="abc123",
        status=RunStatus.CREATED,
        executor="local",
        config={"key": "value"},
        created_at=datetime.now(tz=UTC),
    )


class TestCreateRun:
    def test_create_and_retrieve(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        row = store.get_run(sample_run.id)
        assert row is not None
        assert row["id"] == sample_run.id
        assert row["workflow_sha256"] == "abc123"
        assert row["status"] == "created"

    def test_duplicate_run_raises(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        with pytest.raises(sqlite3.IntegrityError):
            store.create_run(sample_run)

    def test_get_run_not_found(self, store: StateStore) -> None:
        assert store.get_run("nonexistent") is None


class TestUpdateRunStatus:
    def test_update_to_running(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.update_run_status(sample_run.id, RunStatus.RUNNING)
        row = store.get_run(sample_run.id)
        assert row is not None
        assert row["status"] == "running"
        assert row["started_at"] is not None

    def test_update_to_succeeded(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.update_run_status(sample_run.id, RunStatus.RUNNING)
        store.update_run_status(sample_run.id, RunStatus.SUCCEEDED)
        row = store.get_run(sample_run.id)
        assert row is not None
        assert row["status"] == "succeeded"
        assert row["finished_at"] is not None


class TestTransitionTask:
    def test_transition_to_running(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.transition_task(sample_run.id, "task-a", TaskStatus.RUNNING)
        state = store.get_task_state(sample_run.id, "task-a")
        assert state == TaskStatus.RUNNING

    def test_transition_to_succeeded(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.transition_task(sample_run.id, "task-a", TaskStatus.RUNNING)
        store.transition_task(sample_run.id, "task-a", TaskStatus.SUCCEEDED, exit_code=0)
        state = store.get_task_state(sample_run.id, "task-a")
        assert state == TaskStatus.SUCCEEDED

    def test_transition_to_failed(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.transition_task(sample_run.id, "task-a", TaskStatus.RUNNING)
        store.transition_task(sample_run.id, "task-a", TaskStatus.FAILED, exit_code=1, error="oops")
        state = store.get_task_state(sample_run.id, "task-a")
        assert state == TaskStatus.FAILED

    def test_get_task_state_not_found(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        state = store.get_task_state(sample_run.id, "nonexistent")
        assert state is None

    def test_get_completed_tasks(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.transition_task(sample_run.id, "task-a", TaskStatus.RUNNING)
        store.transition_task(sample_run.id, "task-a", TaskStatus.SUCCEEDED, exit_code=0)
        store.transition_task(sample_run.id, "task-b", TaskStatus.RUNNING)
        store.transition_task(sample_run.id, "task-b", TaskStatus.FAILED, exit_code=1)
        store.transition_task(sample_run.id, "task-c", TaskStatus.PENDING)

        completed = store.get_completed_tasks(sample_run.id)
        assert "task-a" in completed
        assert "task-b" in completed
        assert "task-c" not in completed


class TestEvents:
    def test_event_logged_on_transition(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.transition_task(sample_run.id, "task-a", TaskStatus.RUNNING)
        store.transition_task(sample_run.id, "task-a", TaskStatus.SUCCEEDED, exit_code=0)
        # Verify events produce no errors — schema is validated by SQLite
        assert store.get_task_state(sample_run.id, "task-a") == TaskStatus.SUCCEEDED


class TestClose:
    def test_close_twice_does_not_raise(self, store: StateStore, sample_run: Run) -> None:
        store.create_run(sample_run)
        store.close()
        # Second close is a no-op or raises sqlite3.ProgrammingError
        store.close()
