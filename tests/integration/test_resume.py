"""Integration tests for checkpoint + resume functionality."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from sciflow.executors.local import LocalExecutor
from sciflow.models.run import Run, RunStatus, TaskStatus
from sciflow.models.workflow import Task, Workflow
from sciflow.runtime.checkpoint import recovery_point, write_checkpoint
from sciflow.runtime.engine import Engine
from sciflow.runtime.executor import TaskResult
from sciflow.runtime.state import StateStore


class TestCheckpointRoundtrip:
    """Checkpoint write and recovery-point discovery."""

    def test_write_and_discover(self, tmp_path: Path) -> None:
        run = Run(
            id="test-run",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
            run_dir=tmp_path,
        )
        task = Task(id="sim_01", command="echo")
        result = TaskResult(task_id="sim_01", ok=True, exit_code=0)

        path = write_checkpoint(run, task, result)
        assert path.exists()
        assert path.name == "sim_01.json"

        completed = recovery_point(tmp_path)
        assert "sim_01" in completed

    def test_failed_checkpoint_not_in_recovery(self, tmp_path: Path) -> None:
        run = Run(
            id="test-run-2",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
            run_dir=tmp_path,
        )
        task = Task(id="bad_task", command="false")
        result = TaskResult(task_id="bad_task", ok=False, exit_code=1)

        write_checkpoint(run, task, result)
        completed = recovery_point(tmp_path)
        assert "bad_task" not in completed

    def test_recovery_empty_when_no_checkpoints(self, tmp_path: Path) -> None:
        completed = recovery_point(tmp_path)
        assert completed == set()

    def test_recovery_skips_partial_tasks(self, tmp_path: Path) -> None:
        run = Run(
            id="test-run-3",
            workflow_id=uuid4(),
            workflow_sha256="abc",
            status=RunStatus.RUNNING,
            run_dir=tmp_path,
        )
        task1 = Task(id="a", command="echo")
        task2 = Task(id="b", command="echo")
        result_ok = TaskResult(task_id="a", ok=True, exit_code=0)
        result_fail = TaskResult(task_id="b", ok=False, exit_code=1)

        write_checkpoint(run, task1, result_ok)
        write_checkpoint(run, task2, result_fail)

        completed = recovery_point(tmp_path)
        assert "a" in completed
        assert "b" not in completed


class TestEngineResume:
    """Engine resume integration — skips completed tasks."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_tasks(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        store = StateStore(db_path)
        executor = LocalExecutor()

        workflow = Workflow(
            name="resume-test",
            tasks=[
                Task(id="a", command="echo done-a"),
                Task(id="b", command="echo done-b", depends_on=["a"]),
            ],
        )

        # Run the workflow to completion
        engine = Engine(state=store, executor=executor, max_concurrency=2)
        run = await engine.run(
            workflow=workflow,
            run_id="resume-001",
            run_dir=str(tmp_path / "run_dir"),
        )
        assert run.status == RunStatus.SUCCEEDED

        # Verify both tasks are completed in state
        completed = store.get_completed_tasks("resume-001")
        assert "a" in completed
        assert "b" in completed

        # Resume — should succeed with no remaining tasks
        resumed = await engine.resume(
            workflow=workflow,
            run_id="resume-001",
            run_dir=str(tmp_path / "run_dir"),
        )
        assert resumed.status == RunStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_resume_partial_run(self, tmp_path: Path) -> None:
        """Simulate a crash mid-run: task 'a' completes, 'b' does not."""
        db_path = tmp_path / "test.db"
        store = StateStore(db_path)
        executor = LocalExecutor()

        workflow = Workflow(
            name="partial-resume",
            tasks=[
                Task(id="a", command="echo done-a"),
                Task(id="b", command="echo done-b", depends_on=["a"]),
            ],
        )

        # Manually create a run and mark task 'a' as completed
        run = Run(
            id="partial-001",
            workflow_id=workflow.id,
            workflow_sha256=workflow.sha256,
            status=RunStatus.RUNNING,
            executor="local",
            run_dir=tmp_path / "run_dir",
        )
        store.create_run(run)
        store.transition_task(
            run.id, "a", TaskStatus.SUCCEEDED, exit_code=0
        )

        # Engine resume should skip 'a' and run only 'b'
        engine = Engine(state=store, executor=executor, max_concurrency=2)
        resumed = await engine.resume(
            workflow=workflow,
            run_id="partial-001",
            run_dir=str(tmp_path / "run_dir"),
        )
        assert resumed.status == RunStatus.SUCCEEDED

        completed = store.get_completed_tasks("partial-001")
        assert "a" in completed
        assert "b" in completed

    @pytest.mark.asyncio
    async def test_resume_nonexistent_run(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        store = StateStore(db_path)
        executor = LocalExecutor()
        engine = Engine(state=store, executor=executor)

        workflow = Workflow(name="ghost", tasks=[Task(id="x", command="echo")])

        with pytest.raises(ValueError, match="not found"):
            await engine.resume(workflow=workflow, run_id="nonexistent")
