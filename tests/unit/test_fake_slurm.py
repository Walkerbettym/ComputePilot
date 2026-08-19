"""Tests for FakeSlurmExecutor."""

from __future__ import annotations

import pytest

from computepilot.executors.fake_slurm import FakeSlurmExecutor
from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task


@pytest.fixture
def fake_slurm() -> FakeSlurmExecutor:
    return FakeSlurmExecutor()


class TestFakeSlurmSubmit:
    """Tests for FakeSlurmExecutor.submit()."""

    @pytest.mark.asyncio
    async def test_submit_records_task(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test_job", command="echo hello")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        assert handle.task_id == "test_job"
        assert handle.job_id == "fake_1"
        assert len(fake_slurm.submitted) == 1
        assert fake_slurm.submitted[0] is task

    @pytest.mark.asyncio
    async def test_submit_multiple_increments_counter(self, fake_slurm: FakeSlurmExecutor) -> None:
        t1 = Task(id="a", command="cmd_a")
        t2 = Task(id="b", command="cmd_b")
        h1 = await fake_slurm.submit(t1, run_dir="/tmp", env={})
        h2 = await fake_slurm.submit(t2, run_dir="/tmp", env={})
        assert h1.job_id == "fake_1"
        assert h2.job_id == "fake_2"
        assert len(fake_slurm.submitted) == 2


class TestFakeSlurmStatus:
    """Tests for FakeSlurmExecutor.status()."""

    @pytest.mark.asyncio
    async def test_status_always_succeeded(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        status = await fake_slurm.status(handle)
        assert status == TaskStatus.SUCCEEDED


class TestFakeSlurmCollect:
    """Tests for FakeSlurmExecutor.collect()."""

    @pytest.mark.asyncio
    async def test_collect_returns_ok(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        result = await fake_slurm.collect(handle)
        assert result.task_id == "test"
        assert result.ok is True
        assert result.exit_code == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_collect_records_in_completed(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        result = await fake_slurm.collect(handle)
        assert fake_slurm.completed["test"] is result


class TestFakeSlurmCapability:
    """Tests for FakeSlurmExecutor.capability()."""

    def test_supports_gpu_and_partition(self, fake_slurm: FakeSlurmExecutor) -> None:
        cap = fake_slurm.capability()
        assert cap.supports_gpu is True
        assert cap.supports_partition is True
        assert cap.isolation == "job"


class TestFakeSlurmCancel:
    """Tests for FakeSlurmExecutor.cancel()."""

    @pytest.mark.asyncio
    async def test_cancel_does_not_raise(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        await fake_slurm.cancel(handle)
        # Should not raise
        assert True


class TestFakeSlurmLogs:
    """Tests for FakeSlurmExecutor.logs()."""

    @pytest.mark.asyncio
    async def test_logs_returns_empty(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        handle = await fake_slurm.submit(task, run_dir="/tmp", env={})
        logs = await fake_slurm.logs(handle)
        assert logs == ""


class TestFakeSlurmValidate:
    """Tests for FakeSlurmExecutor.validate_task()."""

    def test_validate_returns_empty(self, fake_slurm: FakeSlurmExecutor) -> None:
        task = Task(id="test", command="cmd")
        errors = fake_slurm.validate_task(task)
        assert errors == []


def test_name() -> None:
    assert FakeSlurmExecutor.name == "fake_slurm"
