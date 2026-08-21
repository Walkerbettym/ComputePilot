"""Perf benchmarks for the workflow runtime (NFR-03).

These tests measure:
- 100-task DAG scheduling overhead (< 100ms)
- CLI cold start (< 1s)
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from computepilot.executors.fake_slurm import FakeSlurmExecutor
from computepilot.models.run import RunStatus
from computepilot.models.workflow import Task, Workflow
from computepilot.runtime.engine import Engine
from computepilot.runtime.scheduler import Scheduler
from computepilot.runtime.state import StateStore
from computepilot.workflow.dag import build_dag


@pytest.mark.perf
def test_100_task_scheduling_overhead() -> None:
    """100-task DAG scheduling should take < 100ms (NFR-03)."""
    tasks = [Task(id=f"t{i:03d}", command="echo") for i in range(100)]
    wf = Workflow(name="perf-sched", tasks=tasks)

    start = time.perf_counter()
    dag = build_dag(wf)
    sched = Scheduler(dag, max_concurrency=10)
    elapsed = (time.perf_counter() - start) * 1000  # ms

    assert sched.has_pending()
    assert elapsed < 100, f"Scheduling 100 tasks took {elapsed:.1f}ms (limit 100ms)"


@pytest.mark.perf
def test_100_task_dag_reduce() -> None:
    """Ready-task computation for 100 tasks should be fast."""
    tasks = [
        Task(id=f"t{i:03d}", command="echo", depends_on=[f"t{i - 1:03d}"] if i > 0 else [])
        for i in range(100)
    ]
    wf = Workflow(name="perf-chain", tasks=tasks)
    dag = build_dag(wf)

    start = time.perf_counter()
    completed = set()
    for i in range(100):
        dag.ready_tasks(completed)  # noqa: F841
        completed.add(f"t{i:03d}")
    elapsed = (time.perf_counter() - start) * 1000

    assert elapsed < 50, f"Ready-task computation for 100 tasks took {elapsed:.1f}ms"


@pytest.mark.perf
@pytest.mark.asyncio
async def test_100_task_engine_throughput(tmp_path: Path) -> None:
    """Engine should complete 100 tasks within reasonable time."""
    tasks = [Task(id=f"t{i:03d}", command="echo") for i in range(100)]
    wf = Workflow(name="perf-100", tasks=tasks)

    store = StateStore(tmp_path / "perf.db")
    engine = Engine(
        state=store,
        executor=FakeSlurmExecutor(),
        max_concurrency=20,
        poll_interval=0.01,
    )

    start = time.perf_counter()
    run = await engine.run(wf, run_id="perf-100", run_dir=str(tmp_path))
    elapsed = time.perf_counter() - start

    assert run.status == RunStatus.SUCCEEDED
    assert elapsed < 10.0, f"100 tasks took {elapsed:.2f}s (limit 10s)"


@pytest.mark.perf
def test_1000_task_scheduling_overhead() -> None:
    """1000-task wide DAG scheduling should stay under 1s (v0.5-NFR)."""
    tasks = [Task(id=f"n{i:04d}", command="echo") for i in range(1000)]
    wf = Workflow(name="perf-sched-1k", tasks=tasks)

    start = time.perf_counter()
    dag = build_dag(wf)
    order = dag.topological_order()
    sched = Scheduler(dag, max_concurrency=32)
    elapsed = time.perf_counter() - start

    assert len(order) == 1000
    assert sched.has_pending()
    assert elapsed < 1.0, f"Scheduling 1000 tasks took {elapsed * 1000:.1f}ms (limit 1s)"


@pytest.mark.perf
def test_1000_task_chain_ready_tasks() -> None:
    """Ready-task computation across a 1000-task chain stays under 2s."""
    tasks = [
        Task(id=f"c{i:04d}", command="echo", depends_on=[f"c{i - 1:04d}"] if i > 0 else [])
        for i in range(1000)
    ]
    dag = build_dag(Workflow(name="perf-chain-1k", tasks=tasks))

    start = time.perf_counter()
    completed: set[str] = set()
    for i in range(1000):
        dag.ready_tasks(completed)
        completed.add(f"c{i:04d}")
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, f"Chain ready_tasks x1000 took {elapsed:.2f}s (limit 2s)"
