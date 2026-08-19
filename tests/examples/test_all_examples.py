"""Tests for all example workflows — verify they are valid and runnable."""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.executors.fake_slurm import FakeSlurmExecutor
from computepilot.models.run import RunStatus
from computepilot.runtime.engine import Engine
from computepilot.runtime.scheduler import Scheduler
from computepilot.runtime.state import StateStore
from computepilot.workflow.dag import build_dag
from computepilot.workflow.schema import load_workflow
from computepilot.workflow.validator import validate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def _example_path(name: str) -> Path:
    return EXAMPLES_DIR / name / "workflow.yaml"


# --- Example names and their expected task counts ---
EXAMPLES: list[tuple[str, int]] = [
    ("hello_world", 1),
    ("parameter_sweep", 3),
    ("ml_pipeline", 3),
    ("docker_worker", 2),
    ("data_processing", 3),
]


class TestExampleValidity:
    @pytest.mark.parametrize("name,task_count", EXAMPLES)
    def test_example_valid(self, name: str, task_count: int) -> None:
        """All examples pass validation."""
        path = _example_path(name)
        assert path.exists(), f"Example {name}: workflow.yaml not found"

        wf = load_workflow(path)
        report = validate(wf)
        assert report.passed, (
            f"Example {name}: validation errors: "
            f"{[e.code + ': ' + e.message for e in report.errors]}"
        )

        assert len(wf.tasks) == task_count, (
            f"Example {name}: expected {task_count} tasks, got {len(wf.tasks)}"
        )

    @pytest.mark.parametrize("name,task_count", EXAMPLES)
    def test_example_dag_acyclic(self, name: str, task_count: int) -> None:
        """All examples have acyclic DAGs."""
        path = _example_path(name)
        wf = load_workflow(path)
        dag = build_dag(wf)
        order = dag.topological_order()
        assert len(order) == task_count, (
            f"Example {name}: topological order has {len(order)} tasks, expected {task_count}"
        )

    @pytest.mark.parametrize("name,task_count", EXAMPLES)
    def test_example_scheduler_sequential(self, name: str, task_count: int) -> None:
        """All examples can be scheduled through all tasks."""
        path = _example_path(name)
        wf = load_workflow(path)
        dag = build_dag(wf)
        sched = Scheduler(dag, max_concurrency=task_count)

        completed = set()
        while sched.has_pending():
            ready = sched.ready()
            for t in ready:
                sched.done(t.id)
                completed.add(t.id)

        assert len(completed) == task_count, (
            f"Example {name}: scheduler completed {len(completed)} tasks, expected {task_count}"
        )


class TestExampleExecution:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,task_count", EXAMPLES)
    async def test_example_executes(self, name: str, task_count: int, tmp_path: Path) -> None:
        """All examples execute successfully with FakeSlurmExecutor."""
        path = _example_path(name)
        wf = load_workflow(path)

        store = StateStore(tmp_path / f"{name}.db")
        engine = Engine(state=store, executor=FakeSlurmExecutor(), max_concurrency=task_count)

        run = await engine.run(wf, run_id=f"ex-{name}", run_dir=str(tmp_path / name))
        assert run.status == RunStatus.SUCCEEDED, f"Example {name}: run status {run.status}"

        completed = store.get_completed_tasks(f"ex-{name}")
        assert len(completed) == task_count, (
            f"Example {name}: {len(completed)} completed, expected {task_count}"
        )
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,task_count", [
        ("1000_genomes", 3),
    ])
    async def test_1000_genomes(self, name: str, task_count: int, tmp_path: Path) -> None:
        """1000 Genomes demo executes successfully."""
        path = EXAMPLES_DIR / name / "workflow.yaml"
        assert path.exists(), f"Example {name}: workflow.yaml not found"
        wf = load_workflow(path)
        report = validate(wf)
        assert report.passed, f"Example {name}: validation errors"
        assert len(wf.tasks) == task_count
        store = StateStore(tmp_path / f"{name}.db")
        engine = Engine(state=store, executor=FakeSlurmExecutor(), max_concurrency=task_count)
        run = await engine.run(wf, run_id=f"ex-{name}", run_dir=str(tmp_path / name))
        assert run.status == RunStatus.SUCCEEDED
