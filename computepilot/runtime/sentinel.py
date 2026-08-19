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
        return (self.completed + self.failed) / max(self.total_tasks, 1) * 100

    @property
    def is_stuck(self) -> bool:
        return self.running == 0 and self.completed + self.failed < self.total_tasks


class ExecutionSentinel:
    """Monitor a running workflow — progress and anomaly detection."""

    def __init__(self, state: StateStore, stall_threshold: float = 300.0) -> None:
        self._state = state
        self._stall_threshold = stall_threshold
        self._start_times: dict[str, float] = {}
        self._total_tasks: dict[str, int] = {}

    def watch(self, run_id: str, total_tasks: int) -> None:
        self._start_times[run_id] = time.time()
        self._total_tasks[run_id] = total_tasks

    def unwatch(self, run_id: str) -> None:
        self._start_times.pop(run_id, None)
        self._total_tasks.pop(run_id, None)

    def report_progress(self, run_id: str) -> ProgressReport | None:
        if run_id not in self._total_tasks:
            return None

        total = self._total_tasks[run_id]
        elapsed = time.time() - self._start_times.get(run_id, time.time())
        completed_set = self._state.get_completed_tasks(run_id)

        succeeded = 0
        failed = 0
        for tid in completed_set:
            details = self._state.get_task_details(run_id, tid)
            if details:
                st = details.get("status")
                if st == TaskStatus.SUCCEEDED.value:
                    succeeded += 1
                elif st == TaskStatus.FAILED.value:
                    failed += 1

        anomalies: list[dict[str, Any]] = []

        done = succeeded + failed
        if done < total and elapsed > self._stall_threshold:
            anomalies.append(
                {
                    "task_id": "*",
                    "type": "stalled",
                    "severity": "warning",
                    "description": f"Workflow stalled: {done}/{total} tasks in {elapsed:.0f}s",
                }
            )

        for tid in completed_set:
            d = self._state.get_task_details(run_id, tid)
            is_oom = d and d.get("status") == TaskStatus.FAILED.value and d.get("exit_code") == 137
            if is_oom:
                anomalies.append(
                    {
                        "task_id": tid,
                        "type": "oom",
                        "severity": "critical",
                        "description": f"Task {tid} failed with OOM (exit 137)",
                    }
                )

        return ProgressReport(
            run_id=run_id,
            total_tasks=total,
            completed=succeeded,
            failed=failed,
            running=0,
            pending=max(0, total - succeeded - failed),
            elapsed_seconds=elapsed,
            anomalies=anomalies,
        )

    def detect_anomalies(self, run_id: str) -> list[dict[str, Any]]:
        report = self.report_progress(run_id)
        if report is None:
            return []
        return report.anomalies
