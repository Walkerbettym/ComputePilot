"""Checkpoint writes and recovery-point discovery for workflow runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from computepilot.models.run import Run
from computepilot.models.workflow import Task
from computepilot.runtime.executor import TaskResult


def write_checkpoint(run: Run, task: Task, result: TaskResult) -> Path:
    """Persist a task result to a checkpoint file on disk.

    The checkpoint is written to ``<run.run_dir>/checkpoints/<task.id>.json``.
    Returns the ``Path`` of the written checkpoint file.
    """
    ckpt_dir = Path(run.run_dir) / "checkpoints" if run.run_dir else Path("checkpoints")
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    path = ckpt_dir / f"{task.id}.json"

    data = {
        "task_id": task.id,
        "status": "success" if result.ok else "failed",
        "exit_code": result.exit_code,
        "outputs": result.outputs,
        "error": result.error,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def recovery_point(run_dir: Path) -> set[str]:
    """Return the set of task IDs that have been successfully checkpointed.

    Scans ``<run_dir>/checkpoints/*.json`` and returns IDs whose status
    is ``"success"``.  Returns an empty set when the directory does not
    exist or contains no successful checkpoints.
    """
    ckpt_dir = run_dir / "checkpoints"
    if not ckpt_dir.is_dir():
        return set()

    completed: set[str] = set()
    for f in sorted(ckpt_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if data.get("status") == "success":
                completed.add(data["task_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return completed
