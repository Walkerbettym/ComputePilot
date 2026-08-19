"""Execution Sentinel — monitor workflow progress, detect anomalies."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from computepilot.models.run import TaskStatus
from computepilot.runtime.state import StateStore


@dataclass
class ProgressReport:
    """Progress of a workflow run."""

    run_id: str
    total_tasks: int
    completed: int = 0
    failed: int = 0
    running: int = 0
    pending: int = 0
    elapsed_seconds: float = 0.0
    anomalies: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pct(self) -> float:
        """Completion percentage."""
        return (self.completed + self.failed) / max(self.total_tasks, 1) * 100

    @property
    def is_stuck(self) -> bool:
        """No tasks are running but workflow is not complete."""
        return self.running == 0 and self.completed + self.failed < self.total_tasks


class ExecutionSentinel:
    """Monitor a running workflow — progress and anomaly detection.

    Usage::

        sentinel = ExecutionSentinel(state=store)
        sentinel.watch("run-001", total_tasks=10)

        report = sentinel.report_progress("run-001")
        print(f"{report.pct:.1f}% complete")

        anomalies = sentinel.detect_anomalies("run-001")
        for a in anomalies:
            print(f"⚠️  {a['type']}: {a['description']}")
    """

    def __init__(self, state: StateStore, stall_threshold: float = 300.0) -> None:
        self._state = state
        self._stall_threshold = stall_threshold
        self._start_times: dict[str, float] = {}
        self._total_tasks: dict[str, int] = {}

    def watch(self, run_id: str, total_tasks: int) -> None:
        """Start watching a run."""
        self._start_times[run_id] = time.time()
        self._total_tasks[run_id] = total_tasks

    def unwatch(self, run_id: str) -> None:
        """Stop watching a run."""
        self._start_times.pop(run_id, None)
        self._total_tasks.pop(run_id, None)

    def report_progress(self, run_id: str) -> ProgressReport | None:
        """Generate a progress report for a watched run.

        Returns ``None`` if the run is not being watched.
        """
        if run_id not in self._total_tasks:
            return None

        total = self._total_tasks[run_id]
        elapsed = time.time() - self._start_times.get(run_id, time.time())
        completed_tasks = self._state.get_completed_tasks(run_id)

        completed = len(completed_tasks)
        failed = 0
        running = 0
        pending = max(0, total - completed)

        # Detect anomalies
        anomalies: list[dict[str, Any]] = []

        # Stalled detection
        if completed < total and elapsed > self._stall_threshold:
            anomalies.append(
                {
                    "task_id": "*",
                    "type": "stalled",
                    "severity": "warning",
                    "description": (
                        f"Workflow stalled: {completed}/{total} tasks "
                        f"completed in {elapsed:.0f}s with no progress"
                    ),
                }
            )

        # Check for OOM failures in completed tasks (exit code 137)
        for tid in completed_tasks:
            details = self._state.get_task_details(run_id, tid)
            if details and details.get("status") == TaskStatus.FAILED.value:
                exit_code = details.get("exit_code")
                if exit_code == 137:
                    anomalies.append(
                        {
                            "task_id": tid,
                            "type": "oom",
                            "severity": "critical",
                            "description": (f"Task {tid} failed with OOM (exit code 137)"),
                        }
                    )
                    failed += 1
                else:
                    failed += 1

        # Count running tasks by checking the store
        # (simplified — uses completed count vs total)
        running = max(0, min(total - completed - failed, total))
        pending = max(0, total - completed - failed - running)

        return ProgressReport(
            run_id=run_id,
            total_tasks=total,
            completed=completed,
            failed=failed,
            running=running,
            pending=pending,
            elapsed_seconds=elapsed,
            anomalies=anomalies,
        )

    def detect_anomalies(self, run_id: str) -> list[dict[str, Any]]:
        """Detect anomalies (stalled, OOM, etc.) for a watched run."""
        report = self.report_progress(run_id)
        if report is None:
            return []
        return report.anomalies
