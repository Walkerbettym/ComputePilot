"""Demo 3: Crash recovery — start a run, simulate a crash, resume, verify no data loss.

Tests Engine.resume() in a realistic scenario:
  1. Create a run with 2 tasks (a -> b) and manually mark 'a' as completed
     (simulating a crash partway through).
  2. Call Engine.resume() to pick up where we left off.
  3. Verify task 'a' is NOT re-run and the run completes successfully.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sciflow.executors.local import LocalExecutor
from sciflow.models.run import Run, RunStatus, TaskStatus
from sciflow.models.workflow import Task, Workflow
from sciflow.runtime.engine import Engine
from sciflow.runtime.state import StateStore


class CountingExecutor(LocalExecutor):
    """LocalExecutor wrapper that counts how many tasks are submitted."""

    def __init__(self) -> None:
        super().__init__()
        self.submission_count: int = 0

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> object:
        self.submission_count += 1
        return await super().submit(task, run_dir, env)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_demo_3.db")


@pytest.fixture
def store(db_path: str) -> StateStore:
    return StateStore(db_path)


@pytest.fixture
def executor() -> CountingExecutor:
    return CountingExecutor()


@pytest.mark.asyncio
async def test_demo3_crash_recovery(
    store: StateStore,
    executor: CountingExecutor,
    tmp_path: Path,
) -> None:
    """Simulate a crash mid-run, then resume and verify no data loss."""
    workflow = Workflow(
        name="demo3-crash",
        tasks=[
            Task(id="a", command="bash", args=["-c", "echo done-a > a.txt"]),
            Task(
                id="b",
                command="bash",
                args=["-c", "echo done-b > b.txt"],
                depends_on=["a"],
            ),
        ],
    )

    run_dir = tmp_path / "run_dir"
    run_dir.mkdir(parents=True, exist_ok=True)

    # --- Phase 1: simulate a crash by creating a run with task 'a' completed ---
    # (This is what the state would look like after a real crash mid-run)
    run = Run(
        id="demo3-crash",
        workflow_id=workflow.id,
        workflow_sha256=workflow.sha256,
        status=RunStatus.RUNNING,
        executor="local",
        run_dir=run_dir,
    )
    store.create_run(run)
    store.transition_task("demo3-crash", "a", TaskStatus.SUCCEEDED, exit_code=0)

    # Run task 'a' manually so its output file exists
    a_handle = await executor.submit(workflow.tasks[0], str(run_dir), {})
    a_result = await executor.collect(a_handle)
    assert a_result.ok, "task 'a' should succeed"
    assert (run_dir / "a.txt").exists()
    assert (run_dir / "a.txt").read_text().strip() == "done-a"

    # --- Phase 2: resume the run ---
    resume_engine = Engine(
        state=store,
        executor=executor,
        max_concurrency=1,
        poll_interval=0.25,
    )

    resumed = await resume_engine.resume(
        workflow,
        run_id="demo3-crash",
        run_dir=str(run_dir),
    )

    assert resumed.status == RunStatus.SUCCEEDED, f"resumed run status: {resumed.status}"

    # Task 'a' was submitted once (manually). Task 'b' was submitted once (via resume).
    # Total: 2 submissions. If the engine re-submitted 'a', the count would be higher.
    assert executor.submission_count == 2, (
        f"expected 2 submissions (manual 'a' + resume 'b'), got {executor.submission_count}"
    )

    # Task 'b' should now be complete
    state_b = store.get_task_state("demo3-crash", "b")
    assert state_b == TaskStatus.SUCCEEDED, f"task 'b' state: {state_b}"

    # Output file from task 'b' should exist
    assert (run_dir / "b.txt").exists()
    assert (run_dir / "b.txt").read_text().strip() == "done-b"

    # Both tasks should be in completed set
    completed = store.get_completed_tasks("demo3-crash")
    assert "a" in completed, "task 'a' should be completed"
    assert "b" in completed, "task 'b' should be completed"


@pytest.mark.asyncio
async def test_demo3_resume_nonexistent(
    store: StateStore,
    tmp_path: Path,
) -> None:
    """Resuming a non-existent run raises ValueError."""
    workflow = Workflow(
        name="demo3-ghost",
        tasks=[Task(id="x", command="bash", args=["-c", "echo ghost"])],
    )
    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=1)
    with pytest.raises(ValueError, match="not found"):
        await engine.resume(workflow, run_id="nonexistent")
