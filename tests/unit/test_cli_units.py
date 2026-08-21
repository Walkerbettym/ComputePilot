"""CLI unit tests — direct function invocation (no CliRunner; py3.12+ safe)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import typer

from computepilot.agent.conductor import Conductor, TurnResponse
from computepilot.agent.intent import Intent
from computepilot.cli.commands import artifacts as artifacts_cmd
from computepilot.cli.commands import cancel as cancel_cmd
from computepilot.cli.commands import init as init_cmd
from computepilot.cli.commands import logs as logs_cmd
from computepilot.cli.commands import plan as plan_cmd
from computepilot.cli.commands import report as report_cmd
from computepilot.cli.commands import resume as resume_cmd
from computepilot.cli.commands import run as run_cmd
from computepilot.cli.commands import skill as skill_cmd
from computepilot.cli.commands import status as status_cmd
from computepilot.cli.commands import validate as validate_cmd
from computepilot.cli.ui import (
    build_task_summary,
    print_run_detail,
    print_run_status,
    print_task_logs,
    print_validation_report,
)
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.models.workflow import Task, TaskType, Workflow
from computepilot.runtime.state import StateStore
from computepilot.workflow.validator import ValidationError, ValidationReport

HELLO_YAML = """\
name: hello_world
tasks:
  - id: greet
    command: echo "Hello, ComputePilot!"
    type: shell
"""

CYCLE_YAML = """\
name: bad_cycle
tasks:
  - id: a
    command: x
    type: shell
    depends_on: [b]
  - id: b
    command: y
    type: shell
    depends_on: [a]
"""


def _make_run(run_id: str, status: RunStatus = RunStatus.RUNNING) -> Run:
    return Run(
        id=run_id,
        workflow_id=uuid4(),
        workflow_name="demo",
        workflow_sha256="abc123",
        status=status,
    )


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


@pytest.fixture
def state_db(fake_home: Path) -> Path:
    db = fake_home / ".local" / "share" / "computepilot" / "state.db"
    store = StateStore(db)
    store.create_run(_make_run("r_running"))
    store.update_run_status("r_running", RunStatus.RUNNING)
    store.create_run(_make_run("r_done", RunStatus.SUCCEEDED))
    store.update_run_status("r_done", RunStatus.SUCCEEDED)
    store.transition_task("r_running", "t1", TaskStatus.SUCCEEDED, exit_code=0)
    store.transition_task("r_running", "t2", TaskStatus.FAILED, exit_code=1, error="boom")
    store.record_event("r_running", "t2", "diagnosis", {"cause": "OOM"})
    store.close()
    return db


# -- validate -----------------------------------------------------------------


class TestValidateCmd:
    def test_valid_workflow(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wf = tmp_path / "workflow.yaml"
        wf.write_text(HELLO_YAML)
        validate_cmd.validate_workflow(str(wf))
        assert "validation passed" in capsys.readouterr().out

    def test_missing_file(self) -> None:
        with pytest.raises(typer.Exit) as ei:
            validate_cmd.validate_workflow("/nonexistent/workflow.yaml")
        assert ei.value.exit_code == 2

    def test_unparseable_yaml(self, tmp_path: Path) -> None:
        wf = tmp_path / "broken.yaml"
        wf.write_text(":::: not yaml ::::")
        with pytest.raises(typer.Exit) as ei:
            validate_cmd.validate_workflow(str(wf))
        assert ei.value.exit_code == 2

    def test_failed_validation(self, tmp_path: Path) -> None:
        wf = tmp_path / "cycle.yaml"
        wf.write_text(CYCLE_YAML)
        with pytest.raises(typer.Exit) as ei:
            validate_cmd.validate_workflow(str(wf))
        assert ei.value.exit_code == 1


# -- status -------------------------------------------------------------------


class TestStatusCmd:
    def test_no_db(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            status_cmd.status(None, live=False)
        assert ei.value.exit_code == 0

    def test_list_runs(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_cmd.status(None, live=False)
        out = capsys.readouterr().out
        assert "Recent runs:" in out
        assert "r_running" in out
        assert "r_done" in out

    def test_run_detail(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        status_cmd.status("r_running", live=False)
        out = capsys.readouterr().out
        assert "r_running" in out
        assert "succeeded" in out or "running" in out

    def test_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            status_cmd.status("nope", live=False)
        assert ei.value.exit_code == 1

    def test_live_requires_id(self, state_db: Path) -> None:
        status_cmd.status(None, live=True)

    def test_live_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            status_cmd.status("nope", live=True)
        assert ei.value.exit_code == 1


# -- cancel -------------------------------------------------------------------


class TestCancelCmd:
    def test_cancel_running(self, state_db: Path) -> None:
        cancel_cmd.cancel("r_running")
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM runs WHERE id='r_running'").fetchone()
        conn.close()
        assert row[0] == "cancelled"

    def test_already_terminal(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            cancel_cmd.cancel("r_done")
        assert ei.value.exit_code == 0

    def test_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            cancel_cmd.cancel("nope")
        assert ei.value.exit_code == 1

    def test_no_db(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            cancel_cmd.cancel("whatever")
        assert ei.value.exit_code == 0


# -- logs ---------------------------------------------------------------------


class TestLogsCmd:
    def test_show_events(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        logs_cmd.logs("r_running", task_id=None, tail=50, follow=False)
        out = capsys.readouterr().out
        assert "t1" in out and "t2" in out

    def test_filter_by_task(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        logs_cmd.logs("r_running", task_id="t2", tail=50, follow=False)
        out = capsys.readouterr().out
        assert "t2" in out
        assert "t1" not in out

    def test_tail_limits_rows(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        logs_cmd.logs("r_running", task_id=None, tail=1, follow=False)
        out = capsys.readouterr().out
        assert "t1" not in out and "t2" in out

    def test_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            logs_cmd.logs("nope", task_id=None, tail=50, follow=False)
        assert ei.value.exit_code == 1

    def test_bad_payload_json(self, state_db: Path) -> None:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO task_events (run_id, task_id, event, at, payload) "
            "VALUES ('r_running', 't9', 'custom', '2026-01-01', '{invalid json')"
        )
        conn.commit()
        conn.close()
        logs_cmd.logs("r_running", task_id=None, tail=50, follow=False)

    def test_no_db(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            logs_cmd.logs("whatever", task_id=None, tail=50, follow=False)
        assert ei.value.exit_code == 0


# -- init ---------------------------------------------------------------------


class TestInitCmd:
    def test_scaffold_new(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target = tmp_path / "proj"
        init_cmd.init(str(target), name=None)
        content = (target / "workflow.yaml").read_text()
        assert "my_workflow" in content

    def test_with_name(self, tmp_path: Path) -> None:
        target = tmp_path / "proj"
        init_cmd.init(str(target), name="custom_exp")
        assert "custom_exp" in (target / "workflow.yaml").read_text()

    def test_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "proj"
        target.mkdir()
        (target / "workflow.yaml").write_text("name: x\ntasks: []\n")
        with pytest.raises(typer.Exit) as ei:
            init_cmd.init(str(target))
        assert ei.value.exit_code == 1


# -- artifacts ----------------------------------------------------------------


class TestArtifactsCmd:
    def test_no_db(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            artifacts_cmd.artifacts("whatever")
        assert ei.value.exit_code == 0

    def test_empty_artifacts(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        artifacts_cmd.artifacts("r_done")
        assert "No artifacts found" in capsys.readouterr().out

    def test_list_artifacts(
        self, state_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from computepilot.artifacts.store import ArtifactStore

        f = tmp_path / "result.txt"
        f.write_text("payload")
        store = StateStore(state_db)
        ArtifactStore(store).register("r_done", "t1", f, "result")
        store.close()

        artifacts_cmd.artifacts("r_done")
        out = capsys.readouterr().out
        assert "Artifacts for run r_done" in out
        assert '"type": "result"' in out


# -- report -------------------------------------------------------------------


class TestReportCmd:
    def test_generates_report(
        self, state_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        report_cmd.report("r_done")
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["run_id"] == "r_done"
        text = (tmp_path / "report.md").read_text()
        assert "r_done" in text
        assert "## Code Version" in text

    def test_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            report_cmd.report("nope")
        assert ei.value.exit_code == 1

    def test_no_db(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            report_cmd.report("whatever")
        assert ei.value.exit_code == 1


# -- skill --------------------------------------------------------------------


class TestSkillCmd:
    def test_list_skills(self, capsys: pytest.CaptureFixture[str]) -> None:
        skill_cmd.list_skills()
        out = capsys.readouterr().out
        assert "python" in out

    def test_add_missing_file(self) -> None:
        with pytest.raises(typer.Exit) as ei:
            skill_cmd.add_skill("/nonexistent/skill.yaml")
        assert ei.value.exit_code == 2

    def test_add_skill_yaml(self, tmp_path: Path) -> None:
        p = tmp_path / "my_skill.yaml"
        p.write_text("name: my_skill\nversion: 2.0.0\ndescription: test skill\n")
        skill_cmd.add_skill(str(p))
        assert skill_cmd._registry.get("my_skill") is not None


# -- ui helpers ---------------------------------------------------------------


class TestUiHelpers:
    def test_validation_report_passed(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_validation_report(ValidationReport(), "wf.yaml")
        assert "validation passed" in capsys.readouterr().out

    def test_validation_report_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        report = ValidationReport(
            errors=[
                ValidationError(code="E-001", message="bad", level="error"),
                ValidationError(code="W-101", message="warn", level="warning"),
            ]
        )
        print_validation_report(report)
        out = capsys.readouterr().out
        assert "E-001" in out and "W-101" in out and "error(s)" in out

    def test_print_run_status_all_states(self, capsys: pytest.CaptureFixture[str]) -> None:
        for s in RunStatus:
            print_run_status(_make_run(f"run_{s.value}", s))
        out = capsys.readouterr().out
        for s in ("created", "running", "succeeded", "failed"):
            assert s in out

    def test_print_run_detail_with_tasks(self, capsys: pytest.CaptureFixture[str]) -> None:
        run = _make_run("r1")
        run.started_at = datetime.now(tz=UTC)
        tasks = [{"task_id": "t1", "status": "succeeded", "exit_code": 0, "error": None}]
        print_run_detail(run, tasks)
        assert "r1" in capsys.readouterr().out

    def test_print_task_logs_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_task_logs([])
        assert "No log entries" in capsys.readouterr().out

    def test_print_task_logs_filtered(self, capsys: pytest.CaptureFixture[str]) -> None:
        events = [
            {"task_id": "alpha", "event": "started", "at": "2026-01-01T00:00:00"},
            {"task_id": "beta", "event": "finished", "at": "2026-01-01T00:00:01"},
        ]
        print_task_logs(events, task_id="beta", tail=50)
        out = capsys.readouterr().out
        assert "beta" in out and "finished" in out
        assert "alpha" not in out and "started" not in out

    def test_build_task_summary(self) -> None:
        summary = build_task_summary([{"status": "succeeded"}, {"status": "failed"}])
        assert summary == {"succeeded": 1, "failed": 1}


# -- webui --------------------------------------------------------------------


@pytest.fixture
def webui_db(fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from computepilot.cli import webui

    db = fake_home / ".local" / "share" / "computepilot" / "state.db"
    monkeypatch.setattr(webui, "STATE_DB", db)
    return db


class TestWebUI:
    def test_index_no_db(self, webui_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        client = TestClient(webui.app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "No runs yet" in resp.text

    def test_index_with_runs(self, webui_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        store = StateStore(webui_db)
        store.create_run(_make_run("r_web"))
        store.close()

        client = TestClient(webui.app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Total Runs" in resp.text
        assert "r_web" in resp.text

    def test_run_detail(self, webui_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        store = StateStore(webui_db)
        store.create_run(_make_run("r_web"))
        store.transition_task("r_web", "t1", TaskStatus.SUCCEEDED, exit_code=0)
        conn = sqlite3.connect(str(webui_db))
        conn.execute(
            'UPDATE runs SET config_json=\'{"total_tasks": 1, '
            '"workflow": {"tasks": [{"id": "t1", "type": "shell", "depends_on": []}]}}\' '
            "WHERE id='r_web'"
        )
        conn.commit()
        conn.close()
        store.close()

        client = TestClient(webui.app)
        resp = client.get("/run/r_web")
        assert resp.status_code == 200
        assert "t1" in resp.text
        assert "<svg" in resp.text

    def test_dag_svg_cycle_returns_none(self) -> None:
        from computepilot.cli.webui import dag_svg

        cyclic = [
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["a"]},
        ]
        assert dag_svg(cyclic) is None

    def test_run_detail_bad_config(self, webui_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        store = StateStore(webui_db)
        store.create_run(_make_run("r_badcfg"))
        store.close()
        conn = sqlite3.connect(str(webui_db))
        conn.execute("UPDATE runs SET config_json='{broken' WHERE id='r_badcfg'")
        conn.commit()
        conn.close()

        client = TestClient(webui.app)
        resp = client.get("/run/r_badcfg")
        assert resp.status_code == 200

    def test_run_not_found(self, webui_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        StateStore(webui_db).close()
        client = TestClient(webui.app)
        resp = client.get("/run/ghost")
        assert "not found" in resp.text


# -- provider -----------------------------------------------------------------


class TestOpenAIProvider:
    @staticmethod
    def _make(responder):
        from computepilot.agent.provider import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        provider._client = httpx.Client(
            base_url="https://api.test/v1",
            headers={"Authorization": "Bearer test-key"},
            transport=httpx.MockTransport(responder),
        )
        return provider

    def test_generate(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello"}}],
                    "model": "m1",
                    "usage": {"total_tokens": 7},
                },
            )

        resp = self._make(handler).generate("sys", "user")
        assert resp.content == "hello"
        assert resp.model == "m1"
        assert resp.usage["total_tokens"] == 7

    def test_generate_null_content(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

        assert self._make(handler).generate("sys", "user").content == ""

    def test_structured_output(self) -> None:
        intent_json = json.dumps(
            {
                "verb": "train",
                "target": "model",
                "parameters": {},
                "resources": {"cpu": 1, "memory": "2GB", "gpu": 0},
                "constraints": [],
                "assumptions": [],
            }
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": intent_json}}]})

        resp = self._make(handler).structured_output(Intent, "sys", "user")
        assert isinstance(resp.parsed, Intent)
        assert resp.parsed.verb == "train"

    def test_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        with pytest.raises(httpx.HTTPStatusError):
            self._make(handler).generate("sys", "user")


# -- session persistence ------------------------------------------------------


class TestSessionPersistence:
    def test_roundtrip(self, tmp_path: Path) -> None:
        c1 = Conductor(provider=None)
        sid = c1.new_session()
        session = c1.get_session(sid)
        assert session is not None
        session.current_intent = Intent(verb="shell", target="greet")
        session.phase = "done"

        path = c1.save_session(sid, tmp_path)
        assert path.exists() and path.name == f"{sid}.json"

        c2 = Conductor(provider=None)
        loaded = c2.load_session(sid, tmp_path)
        assert loaded.id == sid
        assert loaded.phase == "done"
        assert loaded.current_intent is not None
        assert loaded.current_intent.verb == "shell"

    def test_save_unknown_session(self, tmp_path: Path) -> None:
        c = Conductor(provider=None)
        with pytest.raises(KeyError):
            c.save_session("ghost", tmp_path)

    def test_load_missing_file(self, tmp_path: Path) -> None:
        c = Conductor(provider=None)
        with pytest.raises(FileNotFoundError):
            c.load_session("ghost", tmp_path)

    def test_list_sessions(self, tmp_path: Path) -> None:
        c = Conductor(provider=None)
        assert c.list_sessions(tmp_path) == []
        s1 = c.new_session()
        s2 = c.new_session()
        c.save_session(s1, tmp_path)
        c.save_session(s2, tmp_path)
        assert c.list_sessions(tmp_path) == sorted([s1, s2])
        assert c.list_sessions(tmp_path / "missing") == []


# -- run command --------------------------------------------------------------


class TestRunCmd:
    def test_missing_workflow(self) -> None:
        with pytest.raises(typer.Exit) as ei:
            run_cmd.run(
                "/nonexistent/wf.yaml",
                executor="local",
                max_concurrency=4,
                approve=True,
                interactive=False,
                from_session=None,
            )
        assert ei.value.exit_code == 2

    def test_invalid_workflow_skips_confirm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = tmp_path / "cycle.yaml"
        wf.write_text(CYCLE_YAML)
        monkeypatch.setattr(
            typer, "confirm", lambda *a, **k: pytest.fail("should not prompt on invalid workflow")
        )
        with pytest.raises(typer.Exit) as ei:
            run_cmd.run(
                str(wf),
                executor="local",
                max_concurrency=4,
                approve=False,
                interactive=False,
                from_session=None,
            )
        assert ei.value.exit_code == 2

    def test_user_aborts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(HELLO_YAML)
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: False)
        with pytest.raises(typer.Exit) as ei:
            run_cmd.run(
                str(wf),
                executor="local",
                max_concurrency=4,
                approve=False,
                interactive=False,
                from_session=None,
            )
        assert ei.value.exit_code == 0

    def test_successful_execution(
        self, fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(HELLO_YAML)
        monkeypatch.chdir(tmp_path)
        run_cmd.run(
            str(wf),
            executor="local",
            max_concurrency=4,
            approve=True,
            interactive=False,
            from_session=None,
        )
        assert "completed successfully" in capsys.readouterr().out

    def test_failing_execution(
        self, fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = tmp_path / "fail.yaml"
        wf.write_text("name: failing\ntasks:\n  - id: boom\n    command: exit 3\n    type: shell\n")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as ei:
            run_cmd.run(
                str(wf),
                executor="local",
                max_concurrency=4,
                approve=True,
                interactive=False,
                from_session=None,
            )
        assert ei.value.exit_code == 1


class TestFromSession:
    def test_unknown_session(self, fake_home: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            run_cmd._run_from_session("ghost", "local", 4)
        assert ei.value.exit_code == 1

    def test_session_without_intent(self, fake_home: Path) -> None:
        conductor = Conductor(provider=None)
        sid = conductor.new_session()
        conductor.save_session(sid, run_cmd._sessions_dir())
        with pytest.raises(typer.Exit) as ei:
            run_cmd._run_from_session(sid, "local", 4)
        assert ei.value.exit_code == 1

    def test_executes_saved_plan(
        self, fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        conductor = Conductor(provider=None)
        sid = conductor.new_session()
        session = conductor.get_session(sid)
        assert session is not None
        session.current_intent = Intent(
            verb="shell", target="greet", parameters={"command": "echo resumed-ok"}
        )
        session.phase = "done"
        conductor.save_session(sid, run_cmd._sessions_dir())

        monkeypatch.chdir(tmp_path)
        run_cmd._run_from_session(sid, "local", 4)
        assert "completed successfully" in capsys.readouterr().out


class TestInteractive:
    def test_happy_path(
        self, fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        calls = {"n": 0}

        def fake_turn_sync(self: Conductor, session_id: str, user_input: str) -> TurnResponse:
            calls["n"] += 1
            if calls["n"] == 1:
                return TurnResponse(message="plan ready", session_id=session_id, phase="approval")
            session = self.get_session(session_id)
            assert session is not None
            session.phase = "done"
            session.current_intent = Intent(
                verb="shell", target="greet", parameters={"command": "echo interactive-ok"}
            )
            return TurnResponse(message="approved", session_id=session_id, phase="done")

        monkeypatch.setattr(Conductor, "turn_sync", fake_turn_sync)
        monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
        monkeypatch.chdir(tmp_path)

        run_cmd._run_interactive("do a thing", "local", 2)
        assert calls["n"] == 2
        out = capsys.readouterr().out
        assert "completed successfully" in out
        assert "--from-session" in out

    def test_reject_then_modify_prompts(
        self,
        fake_home: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        calls = {"n": 0}

        def fake_turn_sync(self: Conductor, session_id: str, user_input: str) -> TurnResponse:
            calls["n"] += 1
            if calls["n"] < 3:
                return TurnResponse(message="plan ready", session_id=session_id, phase="approval")
            session = self.get_session(session_id)
            assert session is not None
            session.phase = "done"
            session.current_intent = Intent(
                verb="shell", target="greet", parameters={"command": "echo revised-ok"}
            )
            return TurnResponse(message="approved", session_id=session_id, phase="done")

        monkeypatch.setattr(Conductor, "turn_sync", fake_turn_sync)
        answers = iter([False, "make it better", True])

        def fake_confirm(*a: object, **k: object) -> bool:
            return next(answers)

        monkeypatch.setattr(typer, "confirm", fake_confirm)
        monkeypatch.setattr(typer, "prompt", lambda *a, **k: next(answers))
        monkeypatch.chdir(tmp_path)

        run_cmd._run_interactive("do a thing", "local", 2)
        assert calls["n"] == 3
        assert "completed successfully" in capsys.readouterr().out


# -- plan ---------------------------------------------------------------------


class TestPlanCmd:
    def test_unsupported_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COMPUTEPILOT_LLM_PROVIDER", "anthropic")
        with pytest.raises(typer.Exit) as ei:
            plan_cmd.plan("do stuff", output=None, model=None, show_cost=True, interactive=False)
        assert ei.value.exit_code == 1

    def test_generate_and_save(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from computepilot.agent.generator import WorkflowGenerator

        wf = Workflow(name="gen_wf", tasks=[Task(id="t1", command="echo hi", type=TaskType.SHELL)])
        monkeypatch.setattr(WorkflowGenerator, "generate", lambda self, desc, model=None: wf)
        out = tmp_path / "out.yaml"
        plan_cmd.plan(
            "desc",
            output=str(out),
            model=None,
            show_cost=True,
            interactive=False,
        )
        captured = capsys.readouterr().out
        assert "Generated workflow" in captured
        assert "Estimated cost" in captured
        assert out.exists() and "gen_wf" in out.read_text()

    def test_generate_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from computepilot.agent.generator import WorkflowGenerator

        def boom(self: object, desc: str, model: str | None = None) -> Workflow:
            raise RuntimeError("llm down")

        monkeypatch.setattr(WorkflowGenerator, "generate", boom)
        with pytest.raises(typer.Exit) as ei:
            plan_cmd.plan("desc", output=None, model=None, show_cost=False, interactive=False)
        assert ei.value.exit_code == 1

    def test_interactive_approval(
        self, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls = {"n": 0}

        def fake_turn_sync(self: Conductor, session_id: str, user_input: str) -> TurnResponse:
            calls["n"] += 1
            if calls["n"] == 1:
                return TurnResponse(message="plan ready", session_id=session_id, phase="approval")
            return TurnResponse(message="approved", session_id=session_id, phase="done")

        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(Conductor, "turn_sync", fake_turn_sync)
            monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
            plan_cmd.plan("desc", output=None, model=None, show_cost=False, interactive=True)
        finally:
            monkeypatch.undo()
        assert calls["n"] == 2


# -- resume -------------------------------------------------------------------


class TestResumeCmd:
    def test_unknown_run(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            resume_cmd.resume("nope", workflow_path="", executor="local", max_concurrency=4)
        assert ei.value.exit_code == 1

    def test_workflow_not_found(
        self, state_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(typer.Exit) as ei:
            resume_cmd.resume("r_done", workflow_path="", executor="local", max_concurrency=4)
        assert ei.value.exit_code == 2

    def test_explicit_workflow_missing(self, state_db: Path) -> None:
        with pytest.raises(typer.Exit) as ei:
            resume_cmd.resume(
                "r_done",
                workflow_path="/nonexistent/wf.yaml",
                executor="local",
                max_concurrency=4,
            )
        assert ei.value.exit_code == 2

    def test_resume_completes(
        self,
        state_db: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(HELLO_YAML)
        monkeypatch.chdir(tmp_path)
        resume_cmd.resume("r_done", workflow_path="", executor="local", max_concurrency=4)
        assert "resumed and completed successfully" in capsys.readouterr().out

    def test_resume_skips_completed_tasks(
        self,
        state_db: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(HELLO_YAML)
        monkeypatch.chdir(tmp_path)
        store = StateStore(state_db)
        store.transition_task("r_done", "greet", TaskStatus.SUCCEEDED, exit_code=0)
        store.close()
        resume_cmd.resume("r_done", workflow_path="", executor="local", max_concurrency=4)
        out = capsys.readouterr().out
        assert "resumed and completed successfully" in out


# -- status --live (completed run breaks the loop immediately) -----------------


class TestLiveProgress:
    def test_completed_run_with_failures(
        self, state_db: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE runs SET config_json='{\"total_tasks\": 2}' WHERE id='r_running'")
        conn.commit()

        from computepilot.cli.commands.status import _live_progress

        _live_progress(conn, "r_running")
        conn.close()
        out = capsys.readouterr().out
        assert "Run finished with 1 failures" in out

    def test_completed_run_success(
        self, state_db: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = StateStore(state_db)
        store.transition_task("r_done", "greet", TaskStatus.SUCCEEDED, exit_code=0)
        store.close()
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE runs SET config_json='{\"total_tasks\": 1}' WHERE id='r_done'")
        conn.commit()

        from computepilot.cli.commands.status import _live_progress

        _live_progress(conn, "r_done")
        conn.close()
        assert "Run completed" in capsys.readouterr().out

    def test_oom_anomaly_reported(self, state_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
        store = StateStore(state_db)
        store.transition_task("r_running", "t2", TaskStatus.FAILED, exit_code=137, error="oom")
        store.close()
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE runs SET config_json='{\"total_tasks\": 2}' WHERE id='r_running'")
        conn.commit()

        from computepilot.cli.commands.status import _live_progress

        _live_progress(conn, "r_running")
        conn.close()
        out = capsys.readouterr().out
        assert "oom" in out
