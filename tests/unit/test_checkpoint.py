"""Unit tests for checkpoint module edge cases (coverage gap)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from computepilot.models.run import Run, RunStatus
from computepilot.models.workflow import Task
from computepilot.runtime.checkpoint import recovery_point, write_checkpoint
from computepilot.runtime.executor import TaskResult


def test_write_checkpoint_no_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """write_checkpoint falls back to ./checkpoints when run.run_dir is None."""
    monkeypatch.chdir(tmp_path)
    run = Run(
        id="r1",
        workflow_id=uuid4(),
        workflow_sha256="abc",
        status=RunStatus.RUNNING,
        run_dir=None,  # key: no run_dir
    )
    task = Task(id="t0", command="echo")
    result = TaskResult(task_id="t0", ok=True, exit_code=0)

    path = write_checkpoint(run, task, result)
    assert path == Path("checkpoints") / "t0.json"
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["status"] == "success"
    assert data["task_id"] == "t0"


def test_write_checkpoint_error_result(tmp_path: Path) -> None:
    """Failed results are marked as failed in the checkpoint file."""
    run = Run(
        id="r2",
        workflow_id=uuid4(),
        workflow_sha256="abc",
        status=RunStatus.RUNNING,
        run_dir=tmp_path,
    )
    task = Task(id="t2", command="false")
    result = TaskResult(
        task_id="t2", ok=False, exit_code=1, error="exit 1", outputs={"o.txt": "sha"}
    )

    path = write_checkpoint(run, task, result)
    data = json.loads(path.read_text())
    assert data["status"] == "failed"
    assert data["exit_code"] == 1
    assert data["error"] == "exit 1"
    assert data["outputs"] == {"o.txt": "sha"}


def test_write_checkpoint_outputs_serialized(tmp_path: Path) -> None:
    """Output checksums are persisted."""
    run = Run(
        id="r3",
        workflow_id=uuid4(),
        workflow_sha256="abc",
        status=RunStatus.SUCCEEDED,
        run_dir=tmp_path,
    )
    task = Task(id="t3", command="python")
    result = TaskResult(
        task_id="t3",
        ok=True,
        exit_code=0,
        outputs={"results.csv": "abcdef123456"},
    )
    path = write_checkpoint(run, task, result)
    data = json.loads(path.read_text())
    assert data["outputs"]["results.csv"] == "abcdef123456"


def test_recovery_skips_malformed_json(tmp_path: Path) -> None:
    """recovery_point silently skips files that aren't valid JSON."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()

    # A valid success checkpoint
    (ckpt_dir / "good.json").write_text(json.dumps({"task_id": "good", "status": "success"}))
    # A corrupted file
    (ckpt_dir / "bad.json").write_text("{ not valid json")
    # A valid JSON but without status key
    (ckpt_dir / "missing.json").write_text(json.dumps({"task_id": "x"}))

    completed = recovery_point(tmp_path)
    assert "good" in completed
    assert "bad" not in completed
    assert "x" not in completed


def test_write_checkpoint_creates_nested_dirs(tmp_path: Path) -> None:
    """write_checkpoint creates checkpoints/ directory."""
    run = Run(
        id="r4",
        workflow_id=uuid4(),
        workflow_sha256="abc",
        status=RunStatus.RUNNING,
        run_dir=tmp_path / "nested" / "run",
    )
    task = Task(id="t4", command="echo")
    result = TaskResult(task_id="t4", ok=True, exit_code=0)
    path = write_checkpoint(run, task, result)
    assert path.exists()
    assert path.parent.name == "checkpoints"
    assert (tmp_path / "nested" / "run" / "checkpoints").is_dir()


def test_recovery_point_sorted_order(tmp_path: Path) -> None:
    """recovery_point processes files in sorted order."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    for name in ["b.json", "a.json", "c.json"]:
        (ckpt_dir / name).write_text(
            json.dumps({"task_id": name.split(".")[0], "status": "success"})
        )
    completed = recovery_point(tmp_path)
    assert completed == {"a", "b", "c"}
