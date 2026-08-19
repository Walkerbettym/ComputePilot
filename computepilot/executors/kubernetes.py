"""Kubernetes executor using kubectl CLI.

Submits tasks as Kubernetes Jobs via ``kubectl run``.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task, TaskType
from computepilot.runtime.executor import ExecutorCapability, Handle, TaskResult


class KubernetesExecutor:
    """Runs tasks as Kubernetes Jobs via kubectl."""

    name = "kubernetes"

    def __init__(
        self,
        image: str = "python:3.11-slim",
        namespace: str = "default",
        kubectl_cmd: str = "kubectl",
    ) -> None:
        self._image = image
        self._namespace = namespace
        self._kubectl = kubectl_cmd
        self._jobs: dict[str, str] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability(
            supports_gpu=True,
            isolation="container",
            supports_timeout_kill=True,
        )

    def validate_task(self, task: Task) -> list[str]:
        errors: list[str] = []
        if task.type == TaskType.SLURM:
            errors.append("kubernetes executor does not support slurm tasks")
        return errors

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        job_name = f"cp-{task.id}".lower()[:63]
        cmd = [self._kubectl, "run", job_name, "--restart=Never"]

        cmd.extend(["--image", task.image or self._image])

        # Command
        if task.args:
            cmd.extend(["--", task.command, *task.args])
        else:
            cmd.extend(["--", *task.command.split()])

        # Env
        for key, val in sorted({**task.environment, **env}.items()):
            cmd.extend(["--env", f"{key}={val}"])

        # Resources
        cmd.extend(["--requests", f"cpu={task.resources.cpu},memory={task.resources.memory}"])
        if task.resources.gpu > 0:
            cmd.extend(["--limits", f"nvidia.com/gpu={task.resources.gpu}"])

        # Namespace
        cmd.extend(["-n", self._namespace])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"kubectl run failed: {stderr.decode(errors='replace').strip()}")

        self._jobs[task.id] = job_name
        return Handle(task_id=task.id, job_id=job_name)

    async def status(self, handle: Handle) -> TaskStatus:
        if handle.job_id is None:
            return TaskStatus.FAILED
        proc = await asyncio.create_subprocess_exec(
            self._kubectl, "get", "pod", handle.job_id,
            "-o", "jsonpath={.status.phase}", "-n", self._namespace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        phase = stdout.decode(errors="replace").strip().upper()

        if phase in ("RUNNING", "PENDING", "CONTAINER_CREATING"):
            return TaskStatus.RUNNING
        if phase == "SUCCEEDED":
            return TaskStatus.SUCCEEDED
        if phase == "FAILED":
            return TaskStatus.FAILED
        return TaskStatus.PENDING if phase in ("", "UNKNOWN") else TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        if handle.job_id is None:
            return
        await asyncio.create_subprocess_exec(
            self._kubectl, "delete", "pod", handle.job_id, "-n", self._namespace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        if handle.job_id is None:
            return ""
        cmd = [self._kubectl, "logs", handle.job_id, "-n", self._namespace]
        if tail > 0:
            cmd.extend(["--tail", str(tail)])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def collect(self, handle: Handle) -> TaskResult:
        status = await self.status(handle)
        log_text = await self.logs(handle)
        ok = status == TaskStatus.SUCCEEDED
        return TaskResult(
            task_id=handle.task_id,
            ok=ok,
            exit_code=0 if ok else 1,
            stdout_tail=log_text,
            error=None if ok else f"task {status.value}",
        )