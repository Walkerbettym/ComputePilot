"""Local subprocess executor."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from pathlib import Path

from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task, TaskType
from computepilot.runtime.executor import ExecutorCapability, Handle, TaskResult


class LocalExecutor:
    """Runs tasks as local subprocesses."""

    name = "local"

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._handles: dict[str, Handle] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        errors: list[str] = []
        if task.resources.gpu > 0:
            errors.append("local executor does not support GPU")
        if task.type == TaskType.SLURM:
            errors.append("local executor does not support slurm tasks")
        return errors

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        if task.type == TaskType.SHELL:
            # Shell tasks get full shell semantics (pipes, redirection, expansion)
            cmd = ["bash", "-c", task.command]
        elif task.args:
            cmd = [task.command, *task.args]
        else:
            cmd = task.command.split()
        full_env = {**os.environ, **task.environment, **env}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir,
            env=full_env,
        )
        handle = Handle(task_id=task.id, pid=proc.pid)
        self._processes[task.id] = proc
        self._handles[task.id] = handle
        return handle

    async def status(self, handle: Handle) -> TaskStatus:
        proc = self._processes.get(handle.task_id)
        if proc is None:
            return TaskStatus.FAILED
        if proc.returncode is None:
            return TaskStatus.RUNNING
        return TaskStatus.SUCCEEDED if proc.returncode == 0 else TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        proc = self._processes.get(handle.task_id)
        if proc:
            proc.kill()

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        proc = self._processes.get(handle.task_id)
        if proc is None or proc.stdout is None:
            return ""
        stdout = await proc.stdout.read()
        lines = stdout.decode(errors="replace").splitlines()
        return "\n".join(lines[-tail:])

    async def collect(self, handle: Handle) -> TaskResult:
        proc = self._processes.get(handle.task_id)
        if proc is None:
            return TaskResult(task_id=handle.task_id, ok=False, exit_code=None, error="no process")
        stdout, stderr = await proc.communicate()
        ok = proc.returncode == 0
        outputs: dict[str, str] = {}
        for path in Path(".").glob("*"):
            if path.is_file() and not path.name.startswith("."):
                outputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

        # Clean up the process reference
        self._processes.pop(handle.task_id, None)
        self._handles.pop(handle.task_id, None)

        return TaskResult(
            task_id=handle.task_id,
            ok=ok,
            exit_code=proc.returncode,
            stdout_tail=stdout.decode(errors="replace"),
            stderr_tail=stderr.decode(errors="replace"),
            error=None if ok else f"exit {proc.returncode}",
            outputs=outputs,
        )

    async def stop(self) -> None:
        """Cancel all running processes and wait for them to finish.

        Ensures subprocess transports are cleaned up before the
        event loop closes, preventing "Event loop is closed" warnings.
        """
        for tid, proc in list(self._processes.items()):
            if proc.returncode is None:
                proc.kill()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
            self._processes.pop(tid, None)
            self._handles.pop(tid, None)
