"""Docker executor using the docker CLI."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from sciflow.models.run import TaskStatus
from sciflow.models.workflow import Task, TaskType
from sciflow.runtime.executor import ExecutorCapability, Handle, TaskResult


def _sanitize_container_name(task_id: str) -> str:
    """Docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-] (max 128)."""
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", task_id)
    return f"cp-{sanitized}"[:128]


class DockerExecutor:
    """Runs tasks as Docker containers via the docker CLI."""

    name = "docker"

    def __init__(self, docker_cmd: str = "docker") -> None:
        self._docker_cmd = docker_cmd
        self._handles: dict[str, Handle] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability(
            supports_gpu=True,
            isolation="container",
            supports_timeout_kill=True,
            max_cpu=0,
            max_memory="",
        )

    def validate_task(self, task: Task) -> list[str]:
        errors: list[str] = []
        if task.type == TaskType.SLURM:
            errors.append("docker executor does not support slurm tasks")
        return errors

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        container_name = _sanitize_container_name(task.id)
        image = task.image or "ubuntu:latest"

        cmd = [self._docker_cmd, "run", "-d", "--name", container_name]

        # Mount run_dir at the same path inside the container
        cmd.extend(["-v", f"{run_dir}:{run_dir}"])

        # Working directory
        cmd.extend(["-w", run_dir])

        # Environment variables
        for key, val in sorted({**task.environment, **env}.items()):
            cmd.extend(["-e", f"{key}={val}"])

        # GPU support
        if task.resources.gpu > 0:
            cmd.append("--gpus")
            cmd.append("all")

        # Resource limits
        if task.resources.memory:
            cmd.extend(["--memory", task.resources.memory])
        if task.resources.cpu > 0:
            cmd.extend(["--cpus", str(task.resources.cpu)])

        # Additional volumes
        for vol in task.volumes:
            cmd.extend(["-v", vol])

        # Image and command
        cmd.append(image)
        cmd.extend(task.command.split())
        if task.args:
            cmd.extend(task.args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        container_id = stdout.decode(errors="replace").strip()
        if proc.returncode != 0 or not container_id:
            raise RuntimeError(f"docker run failed: {stderr.decode(errors='replace').strip()}")

        handle = Handle(task_id=task.id, job_id=container_name)
        self._handles[task.id] = handle
        return handle

    async def status(self, handle: Handle) -> TaskStatus:
        name = handle.job_id or _sanitize_container_name(handle.task_id)
        proc = await asyncio.create_subprocess_exec(
            self._docker_cmd,
            "inspect",
            name,
            "--format={{.State.Status}}|{{.State.ExitCode}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace").strip()

        if "|" in output:
            state, exit_code_str = output.split("|", 1)
        else:
            state = output
            exit_code_str = ""

        if state == "running":
            return TaskStatus.RUNNING
        if state == "exited":
            try:
                exit_code = int(exit_code_str) if exit_code_str else -1
                return TaskStatus.SUCCEEDED if exit_code == 0 else TaskStatus.FAILED
            except ValueError:
                return TaskStatus.FAILED
        if state in ("created", "restarting", "removing", "paused"):
            return TaskStatus.RUNNING
        return TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        name = handle.job_id or _sanitize_container_name(handle.task_id)
        proc = await asyncio.create_subprocess_exec(
            self._docker_cmd,
            "kill",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        name = handle.job_id or _sanitize_container_name(handle.task_id)
        cmd: list[str] = [self._docker_cmd, "logs", name]
        if tail > 0:
            cmd.extend(["--tail", str(tail)])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace")

    async def collect(self, handle: Handle) -> TaskResult:
        name = handle.job_id or _sanitize_container_name(handle.task_id)

        # Wait for container to exit and capture exit code
        proc = await asyncio.create_subprocess_exec(
            self._docker_cmd,
            "wait",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        exit_code_str = stdout.decode(errors="replace").strip()

        try:
            exit_code = int(exit_code_str) if exit_code_str else None
        except ValueError:
            exit_code = None

        # Get all logs
        log_proc = await asyncio.create_subprocess_exec(
            self._docker_cmd,
            "logs",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log_out, _ = await log_proc.communicate()
        log_text = log_out.decode(errors="replace")

        ok = exit_code == 0

        # Collect output file checksums (same pattern as LocalExecutor)
        outputs: dict[str, str] = {}
        for path in Path(".").glob("*"):
            if path.is_file() and not path.name.startswith("."):
                outputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

        result = TaskResult(
            task_id=handle.task_id,
            ok=ok,
            exit_code=exit_code,
            stdout_tail=log_text,
            error=None if ok else f"exit {exit_code}",
            outputs=outputs,
        )

        # Clean up the container
        await asyncio.create_subprocess_exec(
            self._docker_cmd,
            "rm",
            "-f",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return result
