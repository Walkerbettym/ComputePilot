"""Integration tests for the LocalExecutor."""

from __future__ import annotations

import asyncio

import pytest

from sciflow.executors.local import LocalExecutor
from sciflow.models.run import TaskStatus
from sciflow.models.workflow import Task, TaskType


@pytest.mark.asyncio
async def test_local_executor_echo() -> None:
    exe = LocalExecutor()
    task = Task(id="test", command="echo hello")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(0.5)
    status = await exe.status(handle)
    assert status in (TaskStatus.RUNNING, TaskStatus.SUCCEEDED)
    result = await exe.collect(handle)
    assert result.ok
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_local_executor_failing_command() -> None:
    exe = LocalExecutor()
    task = Task(id="fail-test", command="false")
    handle = await exe.submit(task, "/tmp", {})
    result = await exe.collect(handle)
    assert not result.ok
    assert result.exit_code == 1
    assert result.error is not None


@pytest.mark.asyncio
async def test_local_executor_cancel() -> None:
    exe = LocalExecutor()
    task = Task(id="sleep-test", command="sleep 30")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(0.2)
    status = await exe.status(handle)
    assert status == TaskStatus.RUNNING
    await exe.cancel(handle)
    await asyncio.sleep(0.2)
    status = await exe.status(handle)
    assert status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_local_executor_logs() -> None:
    exe = LocalExecutor()
    task = Task(id="log-test", command="echo hello world")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(0.5)
    logs = await exe.logs(handle)
    assert "hello world" in logs


@pytest.mark.asyncio
async def test_local_executor_validate_rejects_gpu() -> None:
    from sciflow.models.workflow import Resources as Res

    exe = LocalExecutor()
    task = Task(
        id="gpu-test",
        command="echo no-gpu",
        resources=Res(gpu=1),
    )
    errors = exe.validate_task(task)
    assert any("GPU" in e for e in errors)


@pytest.mark.asyncio
async def test_local_executor_validate_rejects_slurm() -> None:
    exe = LocalExecutor()
    task = Task(
        id="slurm-test",
        command="sbatch script.sh",
        type=TaskType.SLURM,
    )
    errors = exe.validate_task(task)
    assert any("slurm" in e for e in errors)


@pytest.mark.asyncio
async def test_local_executor_multiple_tasks() -> None:
    exe = LocalExecutor()
    results: dict[str, bool] = {}

    for i in range(3):
        task = Task(id=f"multi-{i}", command=f"echo task-{i}")
        handle = await exe.submit(task, "/tmp", {})
        result = await exe.collect(handle)
        results[task.id] = result.ok

    assert all(results.values())
