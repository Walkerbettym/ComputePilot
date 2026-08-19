"""Demo 4: Reproducibility — same workflow + env + input yields identical artifact checksums.

Tests that running the same workflow twice produces identical output files:
  1. Run a deterministic workflow (compute squares of a fixed parameter list).
  2. Run the same workflow with the same environment again.
  3. Compare the SHA-256 checksums of all output artifacts.
  4. Verify they are identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from computepilot.executors.local import LocalExecutor
from computepilot.models.run import RunStatus
from computepilot.models.workflow import Task, Workflow
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore


@pytest.fixture
def db_path1(tmp_path: Path) -> str:
    return str(tmp_path / "test_demo_4_run1.db")


@pytest.fixture
def db_path2(tmp_path: Path) -> str:
    return str(tmp_path / "test_demo_4_run2.db")


@pytest.fixture
def store1(db_path1: str) -> StateStore:
    return StateStore(db_path1)


@pytest.fixture
def store2(db_path2: str) -> StateStore:
    return StateStore(db_path2)


@pytest.fixture
def executor() -> LocalExecutor:
    return LocalExecutor()


def _file_checksums(run_dir: Path) -> dict[str, str]:
    """Return {filename: sha256} for all output files in *run_dir*."""
    checksums: dict[str, str] = {}
    for f in sorted(run_dir.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            checksums[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return checksums


@pytest.mark.asyncio
async def test_demo4_reproducibility(
    store1: StateStore,
    store2: StateStore,
    executor: LocalExecutor,
    tmp_path: Path,
) -> None:
    """Running the same workflow twice produces identical artifacts."""
    workflow = Workflow(
        name="demo4-repro",
        tasks=[
            Task(
                id="compute",
                command="bash",
                args=[
                    "-c",
                    r"""python3 -c "
import json
params = list(range(1, 11))
results = [x**2 for x in params]
with open('output.json', 'w') as f:
    json.dump({'params': params, 'results': results}, f, sort_keys=True)
with open('checksum.txt', 'w') as f:
    f.write(str(sum(results)))
" """,
                ],
            ),
        ],
    )

    env = {"REPRODUCIBLE": "1"}

    # --- Run 1 ---
    run_dir1 = tmp_path / "run1"
    engine1 = Engine(
        state=store1,
        executor=executor,
        max_concurrency=1,
        poll_interval=0.25,
    )
    run1 = await engine1.run(
        workflow,
        run_id="demo4-run1",
        run_dir=str(run_dir1),
        env=env,
    )
    assert run1.status == RunStatus.SUCCEEDED

    # --- Run 2 ---
    run_dir2 = tmp_path / "run2"
    engine2 = Engine(
        state=store1,
        executor=LocalExecutor(),
        max_concurrency=1,
        poll_interval=0.25,
    )
    run2 = await engine2.run(
        workflow,
        run_id="demo4-run2",
        run_dir=str(run_dir2),
        env=env,
    )
    assert run2.status == RunStatus.SUCCEEDED

    # --- Compare artifact checksums ---
    cs1 = _file_checksums(run_dir1)
    cs2 = _file_checksums(run_dir2)

    assert cs1.keys() == cs2.keys(), f"artifact sets differ: {cs1.keys()} vs {cs2.keys()}"

    for filename in cs1:
        assert cs1[filename] == cs2[filename], (
            f"checksum mismatch for {filename}: {cs1[filename]} != {cs2[filename]}"
        )


@pytest.mark.asyncio
async def test_demo4_different_input_different_output(
    store1: StateStore,
    store2: StateStore,
    executor: LocalExecutor,
    tmp_path: Path,
) -> None:
    """Verify that a different input actually produces different checksums."""
    wf_a = Workflow(
        name="demo4-diff-a",
        tasks=[
            Task(
                id="t",
                command="bash",
                args=["-c", "echo '[1, 2, 3]' > out.json"],
            ),
        ],
    )
    wf_b = Workflow(
        name="demo4-diff-b",
        tasks=[
            Task(
                id="t",
                command="bash",
                args=["-c", "echo '[4, 5, 6]' > out.json"],
            ),
        ],
    )

    engine = Engine(state=store1, executor=executor, max_concurrency=1, poll_interval=0.25)
    r1 = await engine.run(wf_a, run_id="diff-a", run_dir=str(tmp_path / "a"))
    assert r1.status == RunStatus.SUCCEEDED

    engine2 = Engine(state=store2, executor=LocalExecutor(), max_concurrency=1, poll_interval=0.25)
    r2 = await engine2.run(wf_b, run_id="diff-b", run_dir=str(tmp_path / "b"))
    assert r2.status == RunStatus.SUCCEEDED

    cs_a = _file_checksums(tmp_path / "a")
    cs_b = _file_checksums(tmp_path / "b")
    assert cs_a["out.json"] != cs_b["out.json"], (
        "different workflows should produce different checksums"
    )
