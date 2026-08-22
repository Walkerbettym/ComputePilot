"""Tests for v1.3: priority scheduling, /metrics, init --template, status --json."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
import typer

from computepilot.cli.commands import init as init_cmd
from computepilot.cli.commands import status as status_cmd
from computepilot.cli.templates import TEMPLATES
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.models.workflow import Task, Workflow
from computepilot.runtime.scheduler import Scheduler
from computepilot.runtime.state import StateStore
from computepilot.workflow.dag import build_dag


@pytest.fixture
def state_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "shome"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    db = home / ".local/share/computepilot/state.db"
    store = StateStore(db)
    store.create_run(
        Run(id="r_running", workflow_id=uuid4(), workflow_sha256="s", status=RunStatus.RUNNING)
    )
    store.update_run_status("r_running", RunStatus.RUNNING)
    store.create_run(
        Run(id="r_done", workflow_id=uuid4(), workflow_sha256="s", status=RunStatus.SUCCEEDED)
    )
    store.transition_task("r_running", "t1", TaskStatus.SUCCEEDED, exit_code=0)
    store.transition_task("r_running", "t2", TaskStatus.FAILED, exit_code=1, error="boom")
    store.close()
    return db


# -- priority scheduling ---------------------------------------------------------


class TestPriorityScheduling:
    def test_higher_priority_first_single_slot(self) -> None:
        tasks = [
            Task(id=f"t{i}", command="echo", type="shell")
            if False
            else Task(id=f"t{i}", command="echo")
            for i in range(4)
        ]
        tasks[0].priority = 1
        tasks[2].priority = 10
        tasks[3].priority = 5
        dag = build_dag(Workflow(name="prio", tasks=tasks))
        sched = Scheduler(dag, max_concurrency=1)
        first = sched.ready()
        assert [t.id for t in first] == ["t2"]  # priority 10 wins
        sched.done("t2")
        second = sched.ready()
        assert [t.id for t in second] == ["t3"]  # priority 5 next
        sched.done("t3")
        third = sched.ready()
        assert [t.id for t in third] == ["t0"]
        sched.done("t0")
        fourth = sched.ready()
        assert [t.id for t in fourth] == ["t1"]

    def test_default_priority_keeps_topo_order(self) -> None:
        tasks = [Task(id=c, command="echo") for c in "abc"]
        dag = build_dag(Workflow(name="topo", tasks=tasks))
        sched = Scheduler(dag, max_concurrency=10)
        got = [t.id for t in sched.ready()]
        assert got == ["a", "b", "c"]

    def test_priority_ties_break_by_topology(self) -> None:
        tasks = [
            Task(
                id=c,
                command="echo",
            )
            for c in "xyz"
        ]
        for t in tasks:
            t.priority = 7
        dag = build_dag(Workflow(name="ties", tasks=tasks))
        sched = Scheduler(dag, max_concurrency=2)
        got = [t.id for t in sched.ready()]
        assert got == ["x", "y"]

    def test_engine_executes_by_priority(self, tmp_path: Path) -> None:
        """End-to-end: concurrency=1 executes high-priority task first."""
        import asyncio

        from computepilot.executors.local import LocalExecutor
        from computepilot.models.run import RunStatus
        from computepilot.runtime.engine import Engine
        from computepilot.runtime.state import StateStore

        order: list[str] = []

        class Recorder(LocalExecutor):
            async def submit(self, task, run_dir, env):  # type: ignore[override]
                order.append(task.id)
                return await super().submit(task, run_dir, env)

        wf = Workflow(
            name="prio_e2e",
            tasks=[
                Task(id="low", command="echo low"),
                Task(id="high", command="echo high", priority=100),
            ],
        )
        store = StateStore(tmp_path / "s.db")
        engine = Engine(state=store, executor=Recorder(), max_concurrency=1)
        run = asyncio.run(engine.run(wf, run_id="prio-1", run_dir=str(tmp_path)))
        assert run.status == RunStatus.SUCCEEDED
        assert order == ["high", "low"]

    def test_dag_json_includes_priority(self) -> None:
        from computepilot.cli.commands.dag import _to_json

        dag = build_dag(Workflow(name="d", tasks=[Task(id="a", command="x", priority=3)]))
        data = _to_json(dag, ["a"])
        assert data["nodes"][0]["priority"] == 3


# -- /metrics ----------------------------------------------------------------------


@pytest.fixture
def metrics_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    db = home / ".local/share/computepilot/state.db"
    store = StateStore(db)
    store.create_run(
        Run(id="r_m1", workflow_id=uuid4(), workflow_sha256="s", status=RunStatus.SUCCEEDED)
    )
    store.create_run(
        Run(id="r_m2", workflow_id=uuid4(), workflow_sha256="s", status=RunStatus.FAILED)
    )
    store.transition_task("r_m1", "a", TaskStatus.SUCCEEDED, exit_code=0)
    store.transition_task("r_m2", "b", TaskStatus.FAILED, exit_code=1)
    store.close()
    return db


class TestMetricsEndpoint:
    def test_metrics_content(self, metrics_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        monkeypatch.setattr(webui, "STATE_DB", metrics_db)
        client = TestClient(webui.app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "# TYPE computepilot_runs_total counter" in text
        assert 'computepilot_runs_total{status="succeeded"} 1' in text
        assert 'computepilot_runs_total{status="failed"} 1' in text
        assert 'computepilot_tasks_total{status="failed"} 1' in text
        assert "computepilot_artifacts_total 0" in text

    def test_metrics_no_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        monkeypatch.setattr(webui, "STATE_DB", tmp_path / "missing.db")
        client = TestClient(webui.app)
        resp = client.get("/metrics")
        assert 'computepilot_runs_total{status="none"} 0' in resp.text


# -- init --template ----------------------------------------------------------------


class TestInitTemplates:
    @pytest.mark.parametrize("tpl", sorted(TEMPLATES))
    def test_templates_validate(self, tmp_path: Path, tpl: str) -> None:
        target = tmp_path / tpl
        init_cmd.init(str(target), name=None, template=tpl)
        wf_file = target / "workflow.yaml"

        from computepilot.cli.commands.validate import validate_workflow

        validate_workflow(str(wf_file), set_param=None, json_output=False)

    def test_template_with_name(self, tmp_path: Path) -> None:
        init_cmd.init(str(tmp_path / "p"), name="my_sweep", template="parameter_sweep")
        content = (tmp_path / "p" / "workflow.yaml").read_text()
        assert content.splitlines()[0] == "name: my_sweep"

    def test_unknown_template(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            init_cmd.init(str(tmp_path / "x"), name=None, template="nope")
        assert ei.value.exit_code == 2

    def test_foreach_template_expands(self, tmp_path: Path) -> None:
        init_cmd.init(str(tmp_path / "ps"), name=None, template="parameter_sweep")
        wf = load_workflow_safe(tmp_path / "ps" / "workflow.yaml")
        ids = [t.id for t in wf.tasks]
        assert ids == ["setup", "simulate_0", "simulate_1", "simulate_2", "simulate_3", "collect"]


def load_workflow_safe(path: Path):
    from computepilot.workflow.schema import load_workflow

    return load_workflow(path)


# -- status --json -------------------------------------------------------------------


class TestStatusJson:
    def test_list_json(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_cmd.status(None, live=False, json_output=True)
        data = json.loads(capsys.readouterr().out)
        assert {r["id"] for r in data["runs"]} >= {"r_running", "r_done"}

    def test_detail_json(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_cmd.status("r_done", live=False, json_output=True)
        data = json.loads(capsys.readouterr().out)
        assert data["run"]["id"] == "r_done"
        assert isinstance(data["events"], list)

    def test_detail_unknown_exits_1(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            status_cmd.status("ghost", live=False, json_output=True)
        assert ei.value.exit_code == 1
