"""Demo 2: OOM → diagnose → repair → retry → success.

Tests the auto-repair pipeline in Engine:
  1. A task fails with exit code 137 (SIGKILL / OOM).
  2. Engine runs Diagnoser → classifies as OOM → suggests increase_memory.
  3. Engine applies the repair (doubles memory from 2GB → 4GB).
  4. Engine retries the task.
  5. On retry the task succeeds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.agent.diagnosis import Diagnoser
from computepilot.models.run import RunStatus, TaskStatus
from computepilot.models.workflow import Resources, RetryPolicy, Task, Workflow
from computepilot.runtime.engine import Engine
from computepilot.runtime.executor import (
    DiagnosisHandler,
    DiagnosisResult,
    ExecutorCapability,
    Handle,
    RepairSpec,
    TaskResult,
)
from computepilot.runtime.state import StateStore


class DiagnoserAdapter:
    """Adapt the agent-layer Diagnoser to the runtime DiagnosisHandler protocol."""

    def __init__(self, diagnoser: Diagnoser) -> None:
        self._diagnoser = diagnoser

    def diagnose(
        self,
        task_id: str,
        exit_code: int | None = None,
        stderr: str = "",
    ) -> DiagnosisResult:
        d = self._diagnoser.diagnose(task_id, exit_code=exit_code, stderr=stderr)
        return DiagnosisResult(
            task_id=d.task_id,
            cause=d.cause,
            confidence=d.confidence,
            explanation=d.explanation,
            suggested_action=d.suggested_action,
            repair=RepairSpec(action=d.repair.action, params=d.repair.params) if d.repair else None,
        )


assert isinstance(DiagnoserAdapter, type)
# Ensure the adapter satisfies the runtime protocol
_: DiagnosisHandler = DiagnoserAdapter(Diagnoser())


class FakeOOMExecutor:
    """Fake executor that fails once (OOM) then succeeds on retry."""

    name = "fake_oom"

    def __init__(self) -> None:
        self.submission_count: dict[str, int] = {}
        self.submitted_tasks: list[Task] = []

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        self.submitted_tasks.append(task)
        count = self.submission_count.get(task.id, 0) + 1
        self.submission_count[task.id] = count
        return Handle(task_id=task.id)

    async def status(self, handle: Handle) -> TaskStatus:
        count = self.submission_count.get(handle.task_id, 0)
        return TaskStatus.FAILED if count == 1 else TaskStatus.SUCCEEDED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        count = self.submission_count.get(handle.task_id, 0)
        if count == 1:
            return TaskResult(
                task_id=handle.task_id,
                ok=False,
                exit_code=137,
                stderr_tail="Killed (OOM)",
                error="exit 137",
            )
        return TaskResult(
            task_id=handle.task_id,
            ok=True,
            exit_code=0,
        )


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_demo_2.db")


@pytest.fixture
def store(db_path: str) -> StateStore:
    return StateStore(db_path)


@pytest.fixture
def executor() -> FakeOOMExecutor:
    return FakeOOMExecutor()


@pytest.fixture
def diagnosis_handler() -> DiagnosisHandler:
    return DiagnoserAdapter(Diagnoser())


@pytest.mark.asyncio
async def test_oom_diagnose_repair_retry_success(
    store: StateStore,
    executor: FakeOOMExecutor,
    diagnosis_handler: DiagnosisHandler,
    tmp_path: Path,
) -> None:
    """A task that fails with OOM on first attempt is repaired and retried."""
    workflow = Workflow(
        name="demo2-oom",
        tasks=[
            Task(
                id="oom_task",
                command="python",
                args=["-c", "raise SystemExit(137)"],
                resources=Resources(memory="2GB"),
                retry_policy=RetryPolicy(max_attempts=2, retryable_exit_codes=[137]),
            ),
        ],
    )

    engine = Engine(
        state=store,
        executor=executor,
        max_concurrency=1,
        poll_interval=0.01,
        diagnosis_handler=diagnosis_handler,
    )

    run = await engine.run(workflow, run_id="demo2-oom", run_dir=str(tmp_path))

    # --- Assertions ---

    # The run should have succeeded after repair + retry
    assert run.status == RunStatus.SUCCEEDED, f"run status: {run.status}"

    # The task should have been submitted twice (first fail, then succeed)
    assert executor.submission_count.get("oom_task", 0) == 2

    # The task's memory should have been doubled (2GB → 4GB)
    assert workflow.tasks[0].resources.memory == "4GB"

    # State transitions: RUNNING → RETRYING → SUCCEEDED
    oom_state = store.get_task_state("demo2-oom", "oom_task")
    assert oom_state == TaskStatus.SUCCEEDED, f"final state: {oom_state}"


@pytest.mark.asyncio
async def test_oom_without_retry_policy(
    store: StateStore,
    executor: FakeOOMExecutor,
    tmp_path: Path,
) -> None:
    """Without a retry policy allowing retries, the task stays failed."""
    workflow = Workflow(
        name="demo2-no-retry",
        tasks=[
            Task(
                id="oom_task",
                command="python",
                args=["-c", "raise SystemExit(137)"],
                resources=Resources(memory="2GB"),
                retry_policy=RetryPolicy(max_attempts=1),
            ),
        ],
    )

    engine = Engine(
        state=store,
        executor=executor,
        max_concurrency=1,
        poll_interval=0.01,
    )

    await engine.run(workflow, run_id="demo2-no-retry", run_dir=str(tmp_path))

    # Task-level: no retry happened, memory unchanged
    assert executor.submission_count.get("oom_task", 0) == 1
    assert workflow.tasks[0].resources.memory == "2GB"
