"""Slurm executor using sbatch / sacct / scancel CLI."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task
from computepilot.runtime.executor import ExecutorCapability, Handle, TaskResult


def _walltime_to_slurm(total_seconds: int) -> str:
    """Convert seconds to Slurm time format (HH:MM:SS or DD-HH:MM:SS)."""
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _parse_sacct_state(state: str) -> TaskStatus:
    """Map sacct State string to TaskStatus."""
    state = state.strip().upper()
    if state == "COMPLETED":
        return TaskStatus.SUCCEEDED
    if state in ("RUNNING", "COMPLETING", "STAGE_OUT", "RESIZING"):
        return TaskStatus.RUNNING
    if state in ("PENDING", "CONFIGURING", "SUSPENDED", "REQUEUED"):
        return TaskStatus.PENDING
    # FAILED, CANCELLED, TIMEOUT, NODE_FAIL, PREEMPTED, OUT_OF_MEMORY, etc.
    return TaskStatus.FAILED


class SlurmExecutor:
    """Runs tasks as Slurm jobs via sbatch / sacct / scancel."""

    name = "slurm"

    def __init__(
        self,
        sbatch_cmd: str = "sbatch",
        sacct_cmd: str = "sacct",
        scancel_cmd: str = "scancel",
    ) -> None:
        self._sbatch_cmd = sbatch_cmd
        self._sacct_cmd = sacct_cmd
        self._scancel_cmd = scancel_cmd
        self._handles: dict[str, Handle] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability(supports_gpu=True, supports_partition=True, isolation="job")

    def validate_task(self, task: Task) -> list[str]:
        errors: list[str] = []
        if task.resources.cpu < 1:
            errors.append("slurm executor requires cpu >= 1")
        return errors

    def _generate_sbatch_script(self, task: Task, run_dir: str) -> str:
        """Generate an sbatch submission script for the given task."""
        lines = ["#!/bin/bash"]

        # --cpus-per-task
        lines.append(f"#SBATCH --cpus-per-task={task.resources.cpu}")

        # --mem
        lines.append(f"#SBATCH --mem={task.resources.memory}")

        # --gres=gpu:N (only if gpu > 0)
        if task.resources.gpu > 0:
            lines.append(f"#SBATCH --gres=gpu:{task.resources.gpu}")

        # --partition (only if set)
        if task.resources.partition:
            lines.append(f"#SBATCH --partition={task.resources.partition}")

        # --time from walltime
        if task.resources.walltime:
            total_seconds = int(task.resources.walltime.total_seconds())
            lines.append(f"#SBATCH --time={_walltime_to_slurm(total_seconds)}")

        # --chdir
        lines.append(f"#SBATCH --chdir={run_dir}")

        # --output
        lines.append(f"#SBATCH --output={task.id}.out")

        # --job-name
        lines.append(f"#SBATCH --job-name={task.id}")

        # Environment variables (export in the script body)
        if task.environment:
            lines.append("")
            for key, val in sorted(task.environment.items()):
                lines.append(f"export {key}={val}")

        # Blank line before command
        lines.append("")

        # The actual command
        if task.args:
            lines.append(" ".join(task.args))
        else:
            lines.append(task.command)

        return "\n".join(lines) + "\n"

    async def submit(self, task: Task, run_dir: str, env: dict[str, str]) -> Handle:
        script = self._generate_sbatch_script(task, run_dir)

        # Write script to file in run_dir
        script_path = Path(run_dir) / f"{task.id}.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)

        # Run sbatch --parsable
        proc = await asyncio.create_subprocess_exec(
            self._sbatch_cmd,
            "--parsable",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_dir,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace").strip()

        if proc.returncode != 0 or not output:
            raise RuntimeError(f"sbatch failed: {stderr.decode(errors='replace').strip()}")

        # Parse job_id from --parsable output (just the number)
        job_id = output.split(";")[0].strip()
        handle = Handle(task_id=task.id, job_id=job_id)
        self._handles[task.id] = handle
        return handle

    async def status(self, handle: Handle) -> TaskStatus:
        if handle.job_id is None:
            return TaskStatus.FAILED

        proc = await asyncio.create_subprocess_exec(
            self._sacct_cmd,
            "-j",
            handle.job_id,
            "--format=State",
            "--noheader",
            "-P",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        state = stdout.decode(errors="replace").strip()

        if not state:
            return TaskStatus.FAILED

        # sacct may return multiple lines for job steps; take the first non-empty line
        for line in state.splitlines():
            line = line.strip()
            if line:
                return _parse_sacct_state(line)

        return TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        if handle.job_id is None:
            return
        proc = await asyncio.create_subprocess_exec(
            self._scancel_cmd,
            handle.job_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        # Slurm writes stdout to the file specified by --output
        # Look for the output file in the working directory
        output_file = Path(f"{handle.task_id}.out")
        if not output_file.exists():
            return ""
        text = output_file.read_text(errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[-tail:])

    async def collect(self, handle: Handle) -> TaskResult:
        status = await self.status(handle)
        log_text = await self.logs(handle)

        ok = status == TaskStatus.SUCCEEDED
        exit_code = 0 if ok else 1

        # Collect output file checksums
        outputs: dict[str, str] = {}
        for path in Path(".").glob("*"):
            if path.is_file() and not path.name.startswith("."):
                outputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

        return TaskResult(
            task_id=handle.task_id,
            ok=ok,
            exit_code=exit_code,
            stdout_tail=log_text,
            error=None if ok else f"task {status.value}",
            outputs=outputs,
        )
