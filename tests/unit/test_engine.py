"""Comprehensive unit tests for Engine, Scheduler, and Workflow Schema.

Covers uncovered branches for coverage ≥ 80%.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sciflow.executors.local import LocalExecutor
from sciflow.executors.fake_slurm import FakeSlurmExecutor
from sciflow.models.run import Run, RunStatus, TaskStatus
from sciflow.models.workflow import Resources, RetryPolicy, Task, TaskType, Workflow
from sciflow.runtime.checkpoint import recovery_point, write_checkpoint
from sciflow.runtime.engine import Engine
from sciflow.runtime.executor import (
    DiagnosisResult,
    ExecutorCapability,
    Handle,
    RepairSpec,
    TaskResult,
)
from sciflow.runtime.retry import next_delay, should_retry
from sciflow.runtime.scheduler import Scheduler
from sciflow.runtime.state import StateStore
from sciflow.workflow.dag import DAG, build_dag
from sciflow.workflow.schema import dump_workflow, load_workflow
from sciflow.workflow.validator import validate


# =========================================================================
# 1. Engine — validate_task rejection → run fails immediately
# =========================================================================


@pytest.mark.asyncio
async def test_engine_run_validation_rejection(tmp_path: Path) -> None:
    """When executor.validate_task returns errors, run fails immediately."""
    store = StateStore(tmp_path / "test.db")

    class RejectingExecutor(FakeSlurmExecutor):
        name = "rejector"

        def validate_task(self, task: Task) -> list[str]:
            return ["GPU not supported"]

    engine = Engine(state=store, executor=RejectingExecutor(), max_concurrency=1)
    wf = Workflow(name="reject", tasks=[Task(id="a", command="echo")])

    run = await engine.run(wf, run_id="reject-001", run_dir=str(tmp_path))
    assert run.status == RunStatus.FAILED
    assert run.finished_at is not None

    run_data = store.get_run("reject-001")
    assert run_data is not None
    assert run_data["status"] == "failed"


# =========================================================================
# 2. Engine — exception in run() → FAILED + tasks cancelled
# =========================================================================


class _CrashOnSubmit:
    """Executor that raises during submit — simulates crash mid-run."""

    name = "crash_submit"

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(
        self, task: Task, run_dir: str, env: dict[str, str]
    ) -> Handle:
        raise RuntimeError("simulated submit crash")

    async def status(self, handle: Handle) -> TaskStatus:
        return TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        return TaskResult(task_id=handle.task_id, ok=False, exit_code=1)


@pytest.mark.asyncio
async def test_engine_run_exception_cancels_inflight(tmp_path: Path) -> None:
    """An exception during Engine.run sets FAILED and cancels any in-flight."""
    store = StateStore(tmp_path / "test.db")
    engine = Engine(state=store, executor=_CrashOnSubmit(), max_concurrency=1)
    wf = Workflow(name="crash", tasks=[Task(id="a", command="echo")])

    run = await engine.run(wf, run_id="crash-001", run_dir=str(tmp_path))
    assert run.status == RunStatus.FAILED


# =========================================================================
# 3. Engine — resume ValueError on nonexistent run
# =========================================================================


@pytest.mark.asyncio
async def test_engine_resume_nonexistent(tmp_path: Path) -> None:
    """Resume a run that doesn't exist raises ValueError."""
    store = StateStore(tmp_path / "test.db")
    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=1)
    wf = Workflow(name="ghost", tasks=[Task(id="x", command="echo")])

    with pytest.raises(ValueError, match="not found"):
        await engine.resume(workflow=wf, run_id="does-not-exist")


# =========================================================================
# 4. Engine — without diagnosis handler → human_intervention → FAILED
# =========================================================================


class _FakeFailExecutor:
    """Executor that always fails."""

    name = "always_fail"

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(
        self, task: Task, run_dir: str, env: dict[str, str]
    ) -> Handle:
        return Handle(task_id=task.id)

    async def status(self, handle: Handle) -> TaskStatus:
        return TaskStatus.FAILED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        return TaskResult(
            task_id=handle.task_id, ok=False, exit_code=1, error="always fail"
        )


@pytest.mark.asyncio
async def test_engine_run_failure_stops_without_handler(tmp_path: Path) -> None:
    """Without a diagnosis handler, a failed task stops the run as FAILED."""
    store = StateStore(tmp_path / "test.db")
    engine = Engine(
        state=store,
        executor=_FakeFailExecutor(),
        max_concurrency=1,
        diagnosis_handler=None,
    )
    wf = Workflow(
        name="fail-stop",
        tasks=[Task(id="a", command="false", retry_policy=RetryPolicy(max_attempts=1))],
    )

    run = await engine.run(wf, run_id="human-stop", run_dir=str(tmp_path))
    assert run.status == RunStatus.FAILED
    tstate = store.get_task_state("human-stop", "a")
    assert tstate == TaskStatus.FAILED


# =========================================================================
# 5. Engine — OOM repair + retry via diagnosis handler
# =========================================================================


class _OOMOnceExecutor:
    """Fails on first attempt (OOM), succeeds on retry."""

    name = "oom_once"

    def __init__(self) -> None:
        self.count: dict[str, int] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(
        self, task: Task, run_dir: str, env: dict[str, str]
    ) -> Handle:
        c = self.count.get(task.id, 0) + 1
        self.count[task.id] = c
        return Handle(task_id=task.id)

    async def status(self, handle: Handle) -> TaskStatus:
        c = self.count.get(handle.task_id, 0)
        return TaskStatus.FAILED if c == 1 else TaskStatus.SUCCEEDED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        c = self.count.get(handle.task_id, 0)
        if c == 1:
            return TaskResult(
                task_id=handle.task_id,
                ok=False,
                exit_code=137,
                stderr_tail="Killed (OOM)",
                error="exit 137",
            )
        return TaskResult(task_id=handle.task_id, ok=True, exit_code=0)


class _RepairHandler:
    """DiagnosisHandler that always suggests OOM repair."""

    def diagnose(
        self, task_id: str, exit_code: int | None = None, stderr: str = ""
    ) -> DiagnosisResult:
        return DiagnosisResult(
            task_id=task_id,
            cause="OOM",
            confidence=0.9,
            explanation="simulated OOM",
            suggested_action="repair",
            repair=RepairSpec(action="increase_memory", params={"factor": 2.0}),
        )


@pytest.mark.asyncio
async def test_engine_oom_repair_retry(tmp_path: Path) -> None:
    """OOM → diagnosis → increase_memory → retry → success."""
    store = StateStore(tmp_path / "test.db")
    exe = _OOMOnceExecutor()
    engine = Engine(
        state=store,
        executor=exe,
        max_concurrency=1,
        diagnosis_handler=_RepairHandler(),
    )
    wf = Workflow(
        name="oom-repair",
        tasks=[
            Task(
                id="oom",
                command="python",
                args=["-c", "raise SystemExit(137)"],
                resources=Resources(memory="2GB"),
                retry_policy=RetryPolicy(max_attempts=2),
            )
        ],
    )

    run = await engine.run(wf, run_id="oom-repair", run_dir=str(tmp_path))
    assert run.status == RunStatus.SUCCEEDED
    assert exe.count.get("oom", 0) == 2
    assert wf.tasks[0].resources.memory == "4GB"


# =========================================================================
# 6. Engine — plain retry (MISSING_INPUT, no repair)
# =========================================================================


class _RetryOnceExecutor:
    """Fails once on MISSING_INPUT pattern, succeeds on retry."""

    name = "retry_once"

    def __init__(self) -> None:
        self.count: dict[str, int] = {}

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(
        self, task: Task, run_dir: str, env: dict[str, str]
    ) -> Handle:
        c = self.count.get(task.id, 0) + 1
        self.count[task.id] = c
        return Handle(task_id=task.id)

    async def status(self, handle: Handle) -> TaskStatus:
        c = self.count.get(handle.task_id, 0)
        return TaskStatus.FAILED if c == 1 else TaskStatus.SUCCEEDED

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        c = self.count.get(handle.task_id, 0)
        if c == 1:
            return TaskResult(
                task_id=handle.task_id,
                ok=False,
                exit_code=1,
                stderr_tail="No such file or directory",
                error="file not found",
            )
        return TaskResult(task_id=handle.task_id, ok=True, exit_code=0)


class _MissInputHandler:
    """DiagnosisHandler that suggests plain retry for missing input."""

    def diagnose(
        self, task_id: str, exit_code: int | None = None, stderr: str = ""
    ) -> DiagnosisResult:
        return DiagnosisResult(
            task_id=task_id,
            cause="MISSING_INPUT",
            confidence=0.9,
            explanation="file not found",
            suggested_action="retry",
            repair=None,
        )


@pytest.mark.asyncio
async def test_engine_plain_retry(tmp_path: Path) -> None:
    """Missing input → plain retry → success."""
    store = StateStore(tmp_path / "test.db")
    exe = _RetryOnceExecutor()
    engine = Engine(
        state=store,
        executor=exe,
        max_concurrency=1,
        diagnosis_handler=_MissInputHandler(),
    )
    wf = Workflow(
        name="retry-plain",
        tasks=[
            Task(
                id="miss",
                command="cat",
                args=["nonexistent.txt"],
                retry_policy=RetryPolicy(max_attempts=2),
            )
        ],
    )

    run = await engine.run(wf, run_id="retry-plain", run_dir=str(tmp_path))
    assert run.status == RunStatus.SUCCEEDED
    assert exe.count.get("miss", 0) == 2


# =========================================================================
# 7. Engine — apply_repair methods
# =========================================================================


def test_apply_repair_increase_memory() -> None:
    """_apply_repair doubles memory."""
    t = Task(id="t", command="echo", resources=Resources(memory="2GB"))
    repair = RepairSpec(action="increase_memory", params={"factor": 2.0})
    Engine._apply_repair(t, repair)
    assert t.resources.memory == "4GB"


def test_apply_repair_increase_walltime() -> None:
    """_apply_repair increases walltime."""
    t = Task(id="t", command="echo", resources=Resources(walltime=timedelta(hours=2)))
    repair = RepairSpec(action="increase_walltime", params={"factor": 1.5})
    Engine._apply_repair(t, repair)
    assert t.resources.walltime == timedelta(hours=3)


def test_parse_memory() -> None:
    """_parse_memory handles various formats."""
    value, unit = Engine._parse_memory("4GiB")
    assert value == 4 and unit == "GiB"

    value, unit = Engine._parse_memory("512MB")
    assert value == 512 and unit == "MB"

    with pytest.raises(ValueError, match="cannot parse memory"):
        Engine._parse_memory("invalid")


# =========================================================================
# 8. Scheduler — edge cases
# =========================================================================


def test_scheduler_release() -> None:
    """release removes from in_flight without marking completed."""
    wf = Workflow(
        name="release",
        tasks=[
            Task(id="a", command="cmd"),
            Task(id="b", command="cmd", depends_on=["a"]),
        ],
    )
    dag = build_dag(wf)
    sched = Scheduler(dag, max_concurrency=2)

    ready = sched.ready()
    assert ready[0].id == "a"

    sched.release("a")
    assert "a" not in sched.in_flight()
    assert "a" not in sched.completed()

    ready2 = sched.ready()
    assert len(ready2) == 1
    assert ready2[0].id == "a"


def test_scheduler_done_marks_completed() -> None:
    """done adds to completed, removes from in_flight."""
    wf = Workflow(name="done", tasks=[Task(id="a", command="cmd")])
    sched = Scheduler(build_dag(wf), max_concurrency=1)

    _ = sched.ready()
    assert "a" in sched.in_flight()
    sched.done("a")
    assert "a" in sched.completed()
    assert "a" not in sched.in_flight()
    assert not sched.has_pending()


def test_scheduler_has_pending() -> None:
    """has_pending reflects remaining work."""
    wf = Workflow(
        name="pending",
        tasks=[
            Task(id="a", command="cmd"),
            Task(id="b", command="cmd", depends_on=["a"]),
        ],
    )
    sched = Scheduler(build_dag(wf), max_concurrency=2)
    assert sched.has_pending()

    _ = sched.ready()
    sched.done("a")
    r2 = sched.ready()
    assert r2[0].id == "b"
    sched.done("b")
    assert not sched.has_pending()


# =========================================================================
# 9. Workflow Schema
# =========================================================================


def test_schema_load_workflow(tmp_path: Path) -> None:
    """Load valid YAML."""
    yaml_str = "name: my_wf\ntasks:\n  - id: greet\n    command: echo hello\n    type: shell\n"
    path = tmp_path / "workflow.yaml"
    path.write_text(yaml_str)

    wf = load_workflow(path)
    assert wf.name == "my_wf"
    assert len(wf.tasks) == 1
    assert wf.tasks[0].type == TaskType.SHELL
    assert wf.source == path


def test_schema_load_workflow_minimal(tmp_path: Path) -> None:
    """Minimal valid workflow defaults to python type."""
    yaml_str = "name: minimal\ntasks:\n  - id: t\n    command: echo\n"
    path = tmp_path / "minimal.yaml"
    path.write_text(yaml_str)
    wf = load_workflow(path)
    assert wf.name == "minimal"
    assert wf.tasks[0].type == TaskType.PYTHON


def test_schema_dump_roundtrip(tmp_path: Path) -> None:
    """dump → YAML → load preserves fields."""
    expected = Workflow(
        name="roundtrip",
        tasks=[Task(id="a", command="echo")],
    )
    yaml_str = dump_workflow(expected)
    path = tmp_path / "roundtrip.yaml"
    path.write_text(yaml_str)
    restored = load_workflow(path)
    assert restored.name == expected.name
    assert restored.tasks[0].command == expected.tasks[0].command


def test_schema_dump_excludes_id_sha256_source(tmp_path: Path) -> None:
    """dump excludes id, sha256, source (JSON fields)."""
    wf = Workflow(name="exclude", tasks=[Task(id="a", command="echo")])
    yaml_str = dump_workflow(wf)
    assert "sha256" not in yaml_str
    assert "source" not in yaml_str or "source: " not in yaml_str
    assert wf.id.hex not in yaml_str


# =========================================================================
# 10. Resume — previously partial run completes
# =========================================================================


@pytest.mark.asyncio
async def test_engine_resume_partial_fail_task(tmp_path: Path) -> None:
    """Resume skips completed tasks."""
    store = StateStore(tmp_path / "test.db")
    wf = Workflow(
        name="resume-fail",
        tasks=[
            Task(id="a", command="echo", args=["done-a"]),
            Task(id="b", command="echo", args=["done-b"], depends_on=["a"]),
        ],
    )

    run = Run(
        id="resume-fail",
        workflow_id=wf.id,
        workflow_name=wf.name,
        workflow_sha256=wf.sha256,
        status=RunStatus.FAILED,
        executor="local",
        run_dir=tmp_path,
    )
    store.create_run(run)
    store.transition_task("resume-fail", "a", TaskStatus.SUCCEEDED, exit_code=0)

    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=2)
    resumed = await engine.resume(
        workflow=wf, run_id="resume-fail", run_dir=str(tmp_path)
    )
    assert resumed.status == RunStatus.SUCCEEDED
    assert "b" in store.get_completed_tasks("resume-fail")


# =========================================================================
# 11. Resume — exception → FAILED
# =========================================================================


@pytest.mark.asyncio
async def test_engine_resume_exception_marks_failed(tmp_path: Path) -> None:
    """Exception during resume sets run FAILED."""
    store = StateStore(tmp_path / "test.db")
    wf = Workflow(name="resume-crash", tasks=[Task(id="a", command="echo")])
    run = Run(
        id="resume-crash",
        workflow_id=wf.id,
        workflow_name=wf.name,
        workflow_sha256=wf.sha256,
        status=RunStatus.RUNNING,
        executor="local",
        run_dir=tmp_path,
    )
    store.create_run(run)

    engine = Engine(state=store, executor=_CrashOnSubmit(), max_concurrency=1)
    resumed = await engine.resume(
        workflow=wf, run_id="resume-crash", run_dir=str(tmp_path)
    )
    assert resumed.status == RunStatus.FAILED


# =========================================================================
# 12. Engine — watchdog cancels slow task
# =========================================================================


class _SlowExecutor:
    """Executor that stays RUNNING forever."""

    name = "slow"

    def capability(self) -> ExecutorCapability:
        return ExecutorCapability()

    def validate_task(self, task: Task) -> list[str]:
        return []

    async def submit(
        self, task: Task, run_dir: str, env: dict[str, str]
    ) -> Handle:
        return Handle(task_id=task.id)

    async def status(self, handle: Handle) -> TaskStatus:
        return TaskStatus.RUNNING

    async def cancel(self, handle: Handle) -> None:
        return

    async def logs(self, handle: Handle, tail: int = 100) -> str:
        return ""

    async def collect(self, handle: Handle) -> TaskResult:
        return TaskResult(task_id=handle.task_id, ok=False, exit_code=None)


@pytest.mark.asyncio
async def test_engine_watchdog_timeout(tmp_path: Path) -> None:
    """A task exceeding its deadline is cancelled by the watchdog."""
    store = StateStore(tmp_path / "test.db")
    engine = Engine(
        state=store,
        executor=_SlowExecutor(),
        max_concurrency=1,
        poll_interval=0.01,
    )
    wf = Workflow(
        name="slow",
        tasks=[
            Task(
                id="slowpoke",
                command="sleep",
                args=["3600"],
                timeout=timedelta(milliseconds=10),
            )
        ],
    )

    run = await engine.run(wf, run_id="slow-001", run_dir=str(tmp_path))
    assert run.status == RunStatus.FAILED
    task_state = store.get_task_state("slow-001", "slowpoke")
    assert task_state == TaskStatus.FAILED


# =========================================================================
# 13. Engine — run with default run_dir
# =========================================================================


@pytest.mark.asyncio
async def test_engine_run_defaults_run_dir(tmp_path: Path) -> None:
    """When no run_dir supplied, engine uses cwd/runs/<run_id>."""
    store = StateStore(tmp_path / "test.db")
    engine = Engine(state=store, executor=FakeSlurmExecutor(), max_concurrency=1)
    wf = Workflow(name="default-dir", tasks=[Task(id="a", command="echo")])

    run = await engine.run(wf, run_id="default-dir", env={})
    assert run.status == RunStatus.SUCCEEDED
    assert run.run_dir is not None
    assert "runs" in str(run.run_dir)