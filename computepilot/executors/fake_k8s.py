"""Fake Kubernetes executor for CI/testing — records submissions, always succeeds."""

from __future__ import annotations

from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task
from computepilot.runtime.executor import ExecutorCapability, Handle, TaskResult


class FakeKubernetesExecutor:
    """Fake K8s executor — records submitted tasks, always succeeds."""

    name = "fake_k8s"

    def __init__(self) -> None:
        self.submitted: list[Task] = []
        self.completed: dict[str, TaskResult] = {}
        self._counter: int = 0

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability(supports_gpu=True, isolation="container")

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        self.submitted.append(task)
        self._counter += 1
        return Handle(task_id=task.id, job_id=f"k8s-job-{self._counter}")

    async def status(self, handle: Handle) -> TaskStatus:
        return TaskStatus.SUCCEEDED

    async def cancel(self, handle: Handle) -> None:
        pass

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        result = TaskResult(task_id=handle.task_id, ok=True, exit_code=0)
        self.completed[handle.task_id] = result
        return result
