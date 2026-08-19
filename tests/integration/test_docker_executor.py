"""Integration tests for the DockerExecutor."""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from sciflow.executors.docker import DockerExecutor
from sciflow.models.run import TaskStatus
from sciflow.models.workflow import Task, TaskType


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


@pytest.mark.asyncio
async def test_docker_executor_echo() -> None:
    """Verify a simple echo command runs successfully."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    task = Task(id="docker-echo", command="echo hello from docker")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(1)
    status = await exe.status(handle)
    assert status in (TaskStatus.RUNNING, TaskStatus.SUCCEEDED)
    result = await exe.collect(handle)
    assert result.ok
    assert result.exit_code == 0
    assert "hello from docker" in (result.stdout_tail or "")


@pytest.mark.asyncio
async def test_docker_executor_failing_command() -> None:
    """Verify a command that exits non-zero is reported as failed."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    task = Task(id="docker-fail", command="false")
    handle = await exe.submit(task, "/tmp", {})
    result = await exe.collect(handle)
    assert not result.ok
    assert result.exit_code == 1
    assert result.error is not None


@pytest.mark.asyncio
async def test_docker_executor_cancel() -> None:
    """Verify a running container can be cancelled."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    task = Task(id="docker-sleep", command="sleep 30")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(0.5)
    status = await exe.status(handle)
    assert status == TaskStatus.RUNNING
    await exe.cancel(handle)
    await asyncio.sleep(0.5)
    status = await exe.status(handle)
    assert status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_docker_executor_logs() -> None:
    """Verify logs are captured after a command runs."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    task = Task(id="docker-logs", command="echo hello docker world")
    handle = await exe.submit(task, "/tmp", {})
    await asyncio.sleep(1)
    logs = await exe.logs(handle)
    assert "hello docker world" in logs
    await exe.collect(handle)


@pytest.mark.asyncio
async def test_docker_executor_validate_rejects_slurm() -> None:
    """Verify DockerExecutor rejects SLURM tasks."""
    exe = DockerExecutor()
    task = Task(
        id="docker-slurm",
        command="sbatch script.sh",
        type=TaskType.SLURM,
    )
    errors = exe.validate_task(task)
    assert any("slurm" in e for e in errors)


@pytest.mark.asyncio
async def test_docker_executor_validate_accepts_docker() -> None:
    """Verify DockerExecutor accepts DOCKER type tasks."""
    exe = DockerExecutor()
    task = Task(
        id="docker-valid",
        command="echo ok",
        type=TaskType.DOCKER,
    )
    errors = exe.validate_task(task)
    assert len(errors) == 0


@pytest.mark.asyncio
async def test_docker_executor_custom_image() -> None:
    """Verify a custom image can be used."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    task = Task(
        id="docker-alpine",
        command="echo alpine",
        image="alpine:latest",
    )
    handle = await exe.submit(task, "/tmp", {})
    result = await exe.collect(handle)
    assert result.ok
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_docker_executor_env_vars() -> None:
    """Verify environment variables are passed to the container."""
    if not _docker_available():
        pytest.skip("Docker daemon not available")

    exe = DockerExecutor()
    # Use sh -c to ensure shell variable expansion
    task = Task(
        id="docker-env",
        command="sh",
        args=["-c", "echo $MY_VAR"],
        environment={"MY_VAR": "docker_test_value"},
    )
    handle = await exe.submit(task, "/tmp", {})
    result = await exe.collect(handle)
    assert result.ok
    assert "docker_test_value" in (result.stdout_tail or "")
