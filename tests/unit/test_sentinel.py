"""Tests for Execution Sentinel."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.runtime.sentinel import ExecutionSentinel, ProgressReport
from computepilot.runtime.state import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "sentinel.db")


@pytest.fixture
def sentinel(store: StateStore) -> ExecutionSentinel:
    return ExecutionSentinel(state=store)


class TestSentinelProgress:
    @pytest.mark.asyncio
    async def test_watch_and_report(
        self, sentinel: ExecutionSentinel, store: StateStore, tmp_path: Path
    ) -> None:
        """Watch a run and get progress."""
        run = Run(
            id="test-run",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
            run_dir=tmp_path,
        )
        store.create_run(run)
        store.transition_task("test-run", "t1", TaskStatus.RUNNING)

        sentinel.watch("test-run", total_tasks=3)
        report = sentinel.report_progress("test-run")
        assert report is not None
        assert report.run_id == "test-run"
        assert report.total_tasks == 3
        assert report.elapsed_seconds >= 0

    def test_report_unknown_run(self, sentinel: ExecutionSentinel) -> None:
        """Unknown run returns None."""
        report = sentinel.report_progress("nonexistent")
        assert report is None


class TestSentinelAnomaly:
    def test_detect_stalled(
        self, sentinel: ExecutionSentinel, store: StateStore, tmp_path: Path
    ) -> None:
        """Stalled workflow is detected as anomaly."""
        run = Run(
            id="stall-run",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
        )
        store.create_run(run)

        sentinel = ExecutionSentinel(state=store, stall_threshold=0.0)
        sentinel.watch("stall-run", total_tasks=5)

        import time

        time.sleep(0.1)

        anomalies = sentinel.detect_anomalies("stall-run")
        assert len(anomalies) >= 1
        assert anomalies[0]["type"] == "stalled"

    def test_detect_oom(
        self, sentinel: ExecutionSentinel, store: StateStore, tmp_path: Path
    ) -> None:
        """OOM (exit 137) is detected as anomaly."""
        run = Run(
            id="oom-run",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
        )
        store.create_run(run)
        store.transition_task("oom-run", "t1", TaskStatus.FAILED, exit_code=137, error="OOM")
        store.transition_task("oom-run", "t2", TaskStatus.SUCCEEDED, exit_code=0)

        sentinel = ExecutionSentinel(state=store, stall_threshold=999)
        sentinel.watch("oom-run", total_tasks=2)

        anomalies = sentinel.detect_anomalies("oom-run")
        oom_found = any(a["type"] == "oom" for a in anomalies)
        assert oom_found, f"Expected OOM anomaly, got: {anomalies}"

    def test_unknown_run(self, sentinel: ExecutionSentinel) -> None:
        """Unknown run returns empty anomalies."""
        assert sentinel.detect_anomalies("ghost") == []


class TestProgressReport:
    def test_is_stuck(self) -> None:
        """Running tasks → not stuck."""
        report = ProgressReport(run_id="r", total_tasks=10, completed=3, running=1, pending=6)
        assert not report.is_stuck

        report2 = ProgressReport(run_id="r2", total_tasks=10, completed=3, running=0, pending=7)
        assert report2.is_stuck

    def test_pct(self) -> None:
        """Percentage calculated correctly."""
        report = ProgressReport(run_id="r", total_tasks=10, completed=4, failed=1)
        assert abs(report.pct - 50.0) < 0.01
