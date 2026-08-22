"""v1.2: resume --retry-failed closes the failure-recovery loop."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
import typer

from computepilot import api
from computepilot.cli.commands import resume as resume_cmd
from computepilot.executors.local import LocalExecutor
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore
from computepilot.workflow.schema import load_workflow

FLAKY_WF = """\
name: flaky
tasks:
  - id: gate
    command: test -f flag.txt && echo ok || exit 1
    type: shell
"""


def _seed_failed_run(db: Path, wf_path: Path) -> str:
    run_id = f"r_{uuid4().hex[:8]}"
    engine = Engine(state=StateStore(db), executor=LocalExecutor(), max_concurrency=1)
    wf = load_workflow(wf_path)
    import asyncio

    run = asyncio.run(engine.run(workflow=wf, run_id=run_id, run_dir=str(wf_path.parent), env={}))
    assert run.status == RunStatus.FAILED
    return run_id


class TestRetryFailed:
    def test_reset_failed_tasks_deletes_only_failed(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "s.db")
        store.create_run(
            Run(id="r", workflow_id=uuid4(), workflow_sha256="x", status=RunStatus.RUNNING)
        )
        store.transition_task("r", "ok", TaskStatus.SUCCEEDED, exit_code=0)
        store.transition_task("r", "bad", TaskStatus.FAILED, exit_code=1)
        ids = store.reset_failed_tasks("r")
        assert ids == ["bad"]
        assert store.get_task_state("r", "bad") is None
        assert store.get_task_state("r", "ok") == TaskStatus.SUCCEEDED
        store.close()

    def test_resume_without_flag_reports_failure(self, tmp_path: Path) -> None:
        """A resumed run with skipped FAILED tasks must not claim success."""
        (tmp_path / "wf.yaml").write_text(FLAKY_WF)
        db = tmp_path / "state.db"
        run_id = _seed_failed_run(db, tmp_path / "wf.yaml")

        # resume WITHOUT retrying: failed task skipped; run stays FAILED now
        store = StateStore(db)
        engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=1)
        import asyncio

        run = asyncio.run(
            engine.resume(
                workflow=load_workflow(tmp_path / "wf.yaml"),
                run_id=run_id,
                run_dir=tmp_path,
                env={},
            )
        )
        assert run.status == RunStatus.FAILED
        store.close()

    def test_resume_retry_failed_recovers(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "wf.yaml").write_text(FLAKY_WF)
        db = tmp_path / "state.db"
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        state_dir = home / ".local/share/computepilot"
        state_dir.mkdir(parents=True)
        real_db = state_dir / "state.db"
        real_db.write_bytes(db.read_bytes()) if db.exists() else None

        run_id = _seed_failed_run(real_db, tmp_path / "wf.yaml")

        # fix the condition, then CLI-resume with --retry-failed
        monkeypatch.chdir(tmp_path)
        (tmp_path / "flag.txt").write_text("go")
        resume_cmd.resume(
            run_id,
            workflow_path=str(tmp_path / "wf.yaml"),
            executor="local",
            max_concurrency=1,
            retry_failed=True,
        )
        out = capsys.readouterr().out
        assert "Re-queuing 1 failed task(s): gate" in out
        assert "resumed and completed successfully" in out

    def test_api_resume_retry_failed_param(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "wf.yaml").write_text(FLAKY_WF)
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)
        state = tmp_path / "state"
        monkeypatch.setattr(api, "DEFAULT_STATE_DIR", state)

        db = state / "state.db"
        db.parent.mkdir(parents=True)
        run_id = _seed_failed_run(db, tmp_path / "wf.yaml")
        (tmp_path / "flag.txt").write_text("go")

        run = api.resume(run_id, str(tmp_path / "wf.yaml"), state_dir=state, retry_failed=True)
        assert run.status.value == "succeeded"


class TestValidateJson:
    def test_valid_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from computepilot.cli.commands import validate as validate_cmd

        wf = tmp_path / "ok.yaml"
        wf.write_text("name: ok\ntasks:\n  - id: a\n    command: echo hi\n    type: shell\n")
        validate_cmd.validate_workflow(str(wf), set_param=None, json_output=True)
        data = json.loads(capsys.readouterr().out)
        assert data["passed"] is True
        assert all(i["level"] == "warning" for i in data["issues"])

    def test_errors_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from computepilot.cli.commands import validate as validate_cmd

        wf = tmp_path / "cycle.yaml"
        wf.write_text(
            "name: c\ntasks:\n"
            "  - id: a\n    command: x\n    type: shell\n    depends_on: [b]\n"
            "  - id: b\n    command: y\n    type: shell\n    depends_on: [a]\n"
        )
        with pytest.raises(typer.Exit):
            validate_cmd.validate_workflow(str(wf), set_param=None, json_output=True)
        data = json.loads(capsys.readouterr().out)
        assert data["passed"] is False
        assert any(i["level"] == "error" for i in data["issues"])
