"""Demo 1: Parameter sweep workflow end-to-end.

Tests the core Engine pipeline:
  1. Generate parameters file (echo to file)
  2. Simulate (compute squares using shell arithmetic)
  3. Analyze results
  4. Visualize summary

Each task is a real subprocess via LocalExecutor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.executors.local import LocalExecutor
from computepilot.models.run import RunStatus
from computepilot.models.workflow import Task, Workflow
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_demo_1.db")


@pytest.fixture
def store(db_path: str) -> StateStore:
    return StateStore(db_path)


@pytest.fixture
def executor() -> LocalExecutor:
    return LocalExecutor()


@pytest.mark.asyncio
async def test_demo1_parameter_sweep(
    store: StateStore,
    executor: LocalExecutor,
    tmp_path: Path,
) -> None:
    """End-to-end parameter sweep: generate -> simulate -> analyze -> visualize."""
    workflow = Workflow(
        name="demo1-sweep",
        tasks=[
            Task(
                id="generate",
                command="bash",
                args=[
                    "-c",
                    # Generate parameters 1..10 as JSON
                    r"""python3 -c "
import json
with open('parameters.json', 'w') as f:
    json.dump(list(range(1, 11)), f)
" """,
                ],
            ),
            Task(
                id="simulate",
                command="bash",
                args=[
                    "-c",
                    # Compute squares and write results
                    r"""python3 -c "
import json
with open('parameters.json') as f:
    params = json.load(f)
with open('results.json', 'w') as f:
    json.dump([x**2 for x in params], f)
" """,
                ],
                depends_on=["generate"],
            ),
            Task(
                id="analyze",
                command="bash",
                args=[
                    "-c",
                    # Compute statistics
                    r"""python3 -c "
import json
with open('results.json') as f:
    r = json.load(f)
with open('analysis.json', 'w') as f:
    json.dump({'min': min(r), 'max': max(r), 'sum': sum(r), 'mean': sum(r)/len(r)}, f)
" """,
                ],
                depends_on=["simulate"],
            ),
            Task(
                id="visualize",
                command="bash",
                args=[
                    "-c",
                    # Write summary
                    r"""python3 -c "
import json
with open('analysis.json') as f:
    s = json.load(f)
with open('summary.txt', 'w') as f:
    f.write('Parameter Sweep Summary\n')
    f.write(f'Min: {s[\"min\"]}\n')
    f.write(f'Max: {s[\"max\"]}\n')
    f.write(f'Mean: {s[\"mean\"]}\n')
" """,
                ],
                depends_on=["analyze"],
            ),
        ],
    )

    engine = Engine(
        state=store,
        executor=executor,
        max_concurrency=2,
        poll_interval=0.25,
    )

    run = await engine.run(
        workflow,
        run_id="demo1-sweep",
        run_dir=str(tmp_path),
    )

    # --- Assertions ---

    # The workflow should have succeeded
    assert run.status == RunStatus.SUCCEEDED, f"run status: {run.status}"

    # Check all tasks completed in state store
    completed = store.get_completed_tasks("demo1-sweep")
    assert "generate" in completed
    assert "simulate" in completed
    assert "analyze" in completed
    assert "visualize" in completed

    # Check output files exist
    assert (tmp_path / "parameters.json").exists()
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "analysis.json").exists()
    assert (tmp_path / "summary.txt").exists()

    # Verify content correctness
    import json

    params = json.loads((tmp_path / "parameters.json").read_text())
    assert params == list(range(1, 11))

    results = json.loads((tmp_path / "results.json").read_text())
    assert results == [x**2 for x in range(1, 11)]

    summary = (tmp_path / "summary.txt").read_text()
    assert "Min: 1" in summary
    assert "Max: 100" in summary
    assert "Mean: 38.5" in summary


@pytest.mark.asyncio
async def test_demo1_output_artifacts_persist(
    store: StateStore,
    executor: LocalExecutor,
    tmp_path: Path,
) -> None:
    """Verify that even a minimal sweep produces persisted output files."""
    workflow = Workflow(
        name="demo1-minimal",
        tasks=[
            Task(
                id="gen",
                command="bash",
                args=["-c", "echo 'hello' > out.txt"],
            ),
        ],
    )

    engine = Engine(
        state=store,
        executor=executor,
        max_concurrency=2,
        poll_interval=0.25,
    )

    run = await engine.run(
        workflow,
        run_id="demo1-minimal",
        run_dir=str(tmp_path / "minimal"),
    )

    assert run.status == RunStatus.SUCCEEDED
    assert (tmp_path / "minimal" / "out.txt").exists()
    assert (tmp_path / "minimal" / "out.txt").read_text().strip() == "hello"
