"""Fake Slurm executor for CI testing (no real Slurm needed)."""

from __future__ import annotations

from sciflow.models.run import TaskStatus
from sciflow.models.workflow import Task
from sciflow.runtime.executor import ExecutorCapability, Handle, TaskResult


class FakeSlurmExecutor:
    """Records submitted tasks; always succeeds."""

    name = "fake_slurm"

    def __init__(self) -> None:
        self.submitted: list[Task] = []
        self.completed: dict[str, TaskResult] = {}
        self._job_counter: int = 0

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability(supports_gpu=True, supports_partition=True, isolation="job")

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        self.submitted.append(task)
        self._job_counter += 1
        return Handle(task_id=task.id, job_id=f"fake_{self._job_counter}")

    async def status(self, handle: Handle) -> TaskStatus:
        return TaskStatus.SUCCEEDED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        result = TaskResult(
            task_id=handle.task_id,
            ok=True,
            exit_code=0,
            stdout_tail="",
            error=None,
        )
        self.completed[handle.task_id] = result
        return result
