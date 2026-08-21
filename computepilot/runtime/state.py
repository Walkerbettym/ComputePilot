"""SQLite-backed state store for runs, task states, events, and artifacts."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from computepilot.models.run import Run, RunStatus, TaskStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL DEFAULT '',
    workflow_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    executor TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS task_states (
    run_id TEXT NOT NULL REFERENCES runs(id),
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    error TEXT,
    start_time TEXT,
    end_time TEXT,
    PRIMARY KEY (run_id, task_id)
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event TEXT NOT NULL,
    at TEXT NOT NULL,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    path TEXT NOT NULL,
    type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    by TEXT NOT NULL DEFAULT 'user',
    at TEXT NOT NULL,
    options_json TEXT
);
"""


class StateStore:
    """Persistent state store backed by a local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        # WAL improves concurrent read/write (CLI + Dashboard)
        with contextlib.suppress(sqlite3.DatabaseError):
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- Runs ------------------------------------------------------------------

    def create_run(self, run: Run) -> None:
        self._conn.execute(
            "INSERT INTO runs "
            "(id, workflow_id, workflow_name, workflow_sha256, status, "
            "executor, config_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.id,
                str(run.workflow_id),
                run.workflow_name,
                run.workflow_sha256,
                run.status.value,
                run.executor,
                json.dumps(run.config),
                run.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        now = datetime.now().isoformat()
        if status == RunStatus.RUNNING:
            self._conn.execute(
                "UPDATE runs SET status = ?, started_at = ? WHERE id = ?",
                (status.value, now, run_id),
            )
        elif status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
            self._conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (status.value, now, run_id),
            )
        else:
            self._conn.execute(
                "UPDATE runs SET status = ? WHERE id = ?",
                (status.value, run_id),
            )
        self._conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    # -- Task states -----------------------------------------------------------

    def transition_task(
        self,
        run_id: str,
        task_id: str,
        status: TaskStatus,
        attempt: int = 0,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO task_states "
                "(run_id, task_id, status, attempt, exit_code, error, start_time, end_time) "
                "VALUES (?, ?, ?, ?, ?, ?, "
                "CASE WHEN ? = ? THEN ? ELSE NULL END, "
                "CASE WHEN ? IN (?, ?) THEN ? ELSE NULL END)",
                (
                    run_id,
                    task_id,
                    status.value,
                    attempt,
                    exit_code,
                    error,
                    status.value,
                    TaskStatus.RUNNING.value,
                    now,
                    status.value,
                    TaskStatus.SUCCEEDED.value,
                    TaskStatus.FAILED.value,
                    now,
                ),
            )
            self._conn.execute(
                "INSERT INTO task_events (run_id, task_id, event, at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    task_id,
                    status.value,
                    now,
                    json.dumps({"exit_code": exit_code, "error": error}),
                ),
            )

    def record_event(
        self,
        run_id: str,
        task_id: str,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record an arbitrary event for a task (e.g. diagnosis)."""
        now = datetime.now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO task_events (run_id, task_id, event, at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, task_id, event, now, json.dumps(payload) if payload else None),
            )

    def get_task_state(self, run_id: str, task_id: str) -> TaskStatus | None:
        row = self._conn.execute(
            "SELECT status FROM task_states WHERE run_id = ? AND task_id = ?",
            (run_id, task_id),
        ).fetchone()
        if row is None:
            return None
        return TaskStatus(row["status"])

    def get_completed_tasks(self, run_id: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT task_id FROM task_states WHERE run_id = ? AND status IN (?, ?, ?)",
            (run_id, TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.SKIPPED.value),
        ).fetchall()
        return {r["task_id"] for r in rows}

    def get_task_details(self, run_id: str, task_id: str) -> dict[str, Any] | None:
        """Return full details for a specific task in a run."""
        row = self._conn.execute(
            "SELECT task_id, status, attempt, exit_code, error "
            "FROM task_states WHERE run_id = ? AND task_id = ?",
            (run_id, task_id),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
