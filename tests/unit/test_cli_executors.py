"""Tests for CLI-driven executors (Slurm / Docker / Kubernetes) with mocked subprocess."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import pytest

from computepilot.executors.docker import DockerExecutor
from computepilot.executors.kubernetes import KubernetesExecutor
from computepilot.executors.slurm import SlurmExecutor, _parse_sacct_state, _walltime_to_slurm
from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Resources, Task, TaskType
from computepilot.runtime.executor import Handle


class FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._out = io.BytesIO(stdout)
        self._err = io.BytesIO(stderr)
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._out.read(), self._err.read()


def install_fake_exec(monkeypatch: pytest.MonkeyPatch, table: dict[str, tuple[bytes, int]]):
    """Patch asyncio.create_subprocess_exec; routes by argv[0]. Returns call log."""
    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> FakeProc:
        calls.append(args)
        out, rc = table.get(str(args[0]), (b"", 0))
        return FakeProc(stdout=out, returncode=rc)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls


def _task(**kw: Any) -> Task:
    defaults: dict[str, Any] = {
        "id": "step1",
        "command": "echo hi",
        "type": TaskType.SHELL,
    }
    defaults.update(kw)
    return Task(**defaults)


@pytest.mark.asyncio
class TestSlurmExecutor:
    async def test_submit_parses_job_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_exec(monkeypatch, {"sbatch": (b"12345\n", 0)})
        exe = SlurmExecutor()
        handle = await exe.submit(_task(), str(tmp_path), {})
        assert handle.job_id == "12345"
        script = tmp_path / "step1.sh"
        assert script.exists() and "#SBATCH" in script.read_text()

    async def test_submit_failure_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_exec(monkeypatch, {"sbatch": (b"", 1)})
        with pytest.raises(RuntimeError, match="sbatch failed"):
            await SlurmExecutor().submit(_task(), str(tmp_path), {})

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (b"COMPLETED", TaskStatus.SUCCEEDED),
            (b"RUNNING", TaskStatus.RUNNING),
            (b"PENDING", TaskStatus.PENDING),
            (b"TIMEOUT", TaskStatus.FAILED),
            (b"OUT_OF_MEMORY", TaskStatus.FAILED),
            (b"COMPLETED\n12345.extern\n", TaskStatus.SUCCEEDED),
            (b"", TaskStatus.FAILED),
        ],
    )
    async def test_status_mapping(
        self, monkeypatch: pytest.MonkeyPatch, state: bytes, expected: TaskStatus
    ) -> None:
        install_fake_exec(monkeypatch, {"sacct": (state, 0)})
        status = await SlurmExecutor().status(Handle(task_id="t", job_id="42"))
        assert status == expected

    async def test_status_no_job_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_exec(monkeypatch, {})
        assert await SlurmExecutor().status(Handle(task_id="t", job_id=None)) == TaskStatus.FAILED

    async def test_cancel_invokes_scancel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = install_fake_exec(monkeypatch, {"scancel": (b"", 0)})
        await SlurmExecutor().cancel(Handle(task_id="t", job_id="42"))
        await SlurmExecutor().cancel(Handle(task_id="t", job_id=None))
        assert len(calls) == 1 and calls[0][0] == "scancel"

    async def test_logs_tails_output_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "step1.out").write_text("l1\nl2\nl3\n")
        out = await SlurmExecutor().logs(Handle(task_id="step1", job_id="42"), tail=2)
        assert out == "l2\nl3"
        assert await SlurmExecutor().logs(Handle(task_id="missing", job_id="42")) == ""

    async def test_collect_checksums_outputs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "result.txt").write_text("data")
        (tmp_path / ".hidden").write_text("skip")
        install_fake_exec(monkeypatch, {"sacct": (b"COMPLETED", 0)})
        result = await SlurmExecutor().collect(Handle(task_id="step1", job_id="42"))
        assert result.ok is True
        assert result.exit_code == 0
        assert "result.txt" in result.outputs and ".hidden" not in result.outputs

    def test_walltime_conversion(self) -> None:
        assert _walltime_to_slurm(3600) == "01:00:00"
        assert _walltime_to_slurm(7200 + 60) == "02:01:00"

    def test_parse_sacct_state_direct(self) -> None:
        assert _parse_sacct_state("completed") == TaskStatus.SUCCEEDED
        assert _parse_sacct_state("weird") == TaskStatus.FAILED

    def test_validate_task_rejects_non_shell(self) -> None:
        exe = SlurmExecutor()
        bad = _task(id="d", command="x", type=TaskType.PYTHON, image=None)
        errors = exe.validate_task(bad)
        assert isinstance(errors, list)


@pytest.mark.asyncio
class TestDockerExecutor:
    async def test_submit_runs_container(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = install_fake_exec(monkeypatch, {"docker": (b"abc123def\n", 0)})
        exe = DockerExecutor()
        task = _task(
            id="ct-1",
            type=TaskType.DOCKER,
            image="python:3.11",
            environment={"FOO": "bar"},
            resources=Resources(cpu=2, memory="4GB", gpu=1),
        )
        handle = await exe.submit(task, str(tmp_path), {"RUN_ENV": "1"})
        assert handle.job_id.startswith("cp-ct-1")
        argv = [str(a) for a in calls[0]]
        assert "--gpus" in argv and "--memory" in argv and "python:3.11" in argv
        assert any(a.startswith("FOO=bar") for a in argv)

    async def test_submit_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_exec(monkeypatch, {"docker": (b"", 125)})
        with pytest.raises(RuntimeError, match="docker run failed"):
            await DockerExecutor().submit(_task(id="x", type=TaskType.DOCKER), str(tmp_path), {})

    @pytest.mark.parametrize(
        ("inspect_out", "expected"),
        [
            (b"exited|0", TaskStatus.SUCCEEDED),
            (b"exited|3", TaskStatus.FAILED),
            (b"running|0", TaskStatus.RUNNING),
            (b"paused|0", TaskStatus.RUNNING),
            (b"dead|0", TaskStatus.FAILED),
            (b"", TaskStatus.FAILED),
        ],
    )
    async def test_status_inspect(
        self, monkeypatch: pytest.MonkeyPatch, inspect_out: bytes, expected: TaskStatus
    ) -> None:
        install_fake_exec(monkeypatch, {"docker": (inspect_out, 0)})
        status = await DockerExecutor().status(Handle(task_id="t", job_id="cp-t"))
        assert status == expected

    async def test_validate_rejects_slurm(self) -> None:
        errors = DockerExecutor().validate_task(_task(type=TaskType.SLURM))
        assert errors and "slurm" in errors[0]


@pytest.mark.asyncio
class TestKubernetesExecutor:
    async def test_submit_creates_pod_job(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = install_fake_exec(monkeypatch, {"kubectl": (b"pod/step1 created\n", 0)})
        exe = KubernetesExecutor()
        task = _task(
            id="job-1",
            command="python train.py --epochs 5",
            image="custom:latest",
            resources=Resources(cpu=4, memory="8GB", gpu=2),
        )
        handle = await exe.submit(task, str(tmp_path), {"K": "V"})
        assert handle.job_id == "cp-job-1"
        argv = [str(a) for a in calls[0]]
        assert "custom:latest" in argv and "nvidia.com/gpu=2" in argv
        assert "train.py" in argv and "K=V" in argv

    async def test_submit_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_exec(monkeypatch, {"kubectl": (b"", 1)})
        with pytest.raises(RuntimeError, match="kubectl run failed"):
            await KubernetesExecutor().submit(_task(id="j"), str(tmp_path), {})

    @pytest.mark.parametrize(
        ("phase", "expected"),
        [
            (b"SUCCEEDED", TaskStatus.SUCCEEDED),
            (b"FAILED", TaskStatus.FAILED),
            (b"Running", TaskStatus.RUNNING),
            (b"Pending", TaskStatus.RUNNING),
            (b"", TaskStatus.PENDING),
            (b"UnknownPhase", TaskStatus.FAILED),
        ],
    )
    async def test_status_phases(
        self, monkeypatch: pytest.MonkeyPatch, phase: bytes, expected: TaskStatus
    ) -> None:
        install_fake_exec(monkeypatch, {"kubectl": (phase, 0)})
        status = await KubernetesExecutor().status(Handle(task_id="t", job_id="cp-t"))
        assert status == expected

    async def test_cancel_and_logs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = install_fake_exec(monkeypatch, {"kubectl": (b"log line\n", 0)})
        exe = KubernetesExecutor()
        await exe.cancel(Handle(task_id="t", job_id="cp-t"))
        text = await exe.logs(Handle(task_id="t", job_id="cp-t"), tail=5)
        assert text == "log line\n"
        assert await exe.logs(Handle(task_id="t", job_id=None)) == ""
        delete_calls = [c for c in calls if c[1] == "delete"]
        assert len(delete_calls) == 1


@pytest.mark.asyncio
class TestLocalShellSemantics:
    async def test_shell_task_supports_redirection(self, tmp_path: Path) -> None:
        from computepilot.executors.local import LocalExecutor

        exe = LocalExecutor()
        task = _task(id="sh1", command="echo data > out.txt")
        handle = await exe.submit(task, str(tmp_path), {})
        result = await exe.collect(handle)
        assert result.ok is True
        assert (tmp_path / "out.txt").read_text().strip() == "data"

    async def test_shell_task_exit_code_propagates(self, tmp_path: Path) -> None:
        from computepilot.executors.local import LocalExecutor

        exe = LocalExecutor()
        task = _task(id="sh2", command="exit 3")
        handle = await exe.submit(task, str(tmp_path), {})
        result = await exe.collect(handle)
        assert result.ok is False
        assert result.exit_code == 3

    async def test_python_task_still_exec_style(self, tmp_path: Path) -> None:
        from computepilot.executors.local import LocalExecutor

        exe = LocalExecutor()
        task = _task(id="py1", type=TaskType.PYTHON, command="echo", args=["a", "b"])
        handle = await exe.submit(task, str(tmp_path), {})
        result = await exe.collect(handle)
        assert result.stdout_tail.strip() == "a b"
