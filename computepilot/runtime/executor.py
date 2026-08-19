"""Executor protocol, result types, and handle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task


@dataclass
class ExecutorCapability:
    """Declares what an executor supports."""

    supports_gpu: bool = False
    supports_partition: bool = False
    supports_timeout_kill: bool = True
    isolation: str = "process"
    max_cpu: int = 0
    max_memory: str = ""


@dataclass
class TaskResult:
    """Outcome of a finished task."""

    task_id: str
    ok: bool
    exit_code: int | None
    signal: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)  # path → sha256


@dataclass
class Handle:
    """Opaque handle returned after submitting a task."""

    task_id: str
    pid: int | None = None
    job_id: str | None = None


@runtime_checkable
class Executor(Protocol):
    """Protocol every executor must satisfy."""

    name: str

    def capability(self) -> ExecutorCapability: ...
    def validate_task(self, task: Task) -> list[str]: ...
    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle: ...
    async def status(self, handle: Handle) -> TaskStatus: ...
    async def cancel(self, handle: Handle) -> None: ...
    async def logs(self, handle: Handle, tail: int = 100) -> str: ...
    async def collect(self, handle: Handle) -> TaskResult: ...


@dataclass
class RepairSpec:
    """Repair action specification for a failed task."""

    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisResult:
    """Result of a failure diagnosis."""

    task_id: str = ""
    cause: str = "UNKNOWN"
    confidence: float = 0.0
    explanation: str = ""
    suggested_action: str = "human"
    repair: RepairSpec | None = None


class DiagnosisHandler(Protocol):
    """Protocol for failure diagnosis handlers."""

    def diagnose(
        self, task_id: str, exit_code: int | None, stderr: str = ""
    ) -> DiagnosisResult: ...
