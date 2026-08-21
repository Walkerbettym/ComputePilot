"""Tests for cpilot sessions list/show/clean."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
import typer

from computepilot.agent.conductor import Conductor
from computepilot.agent.intent import Intent
from computepilot.cli.commands import sessions as sessions_cmd
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.runtime.state import StateStore


@pytest.fixture
def saved_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    conductor = Conductor(provider=None)
    sid = conductor.new_session()
    session = conductor.get_session(sid)
    assert session is not None
    session.phase = "done"
    session.current_intent = Intent(verb="train", target="resnet50", parameters={"epochs": 10})
    conductor.save_session(sid, sessions_cmd._sessions_dir())
    return sid


class TestSessionsCmd:
    def test_list_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        home = tmp_path / "h2"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        sessions_cmd.list_sessions_cmd()
        assert "No saved sessions" in capsys.readouterr().out

    def test_list_shows_session(
        self, saved_session: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sessions_cmd.list_sessions_cmd()
        out = capsys.readouterr().out
        assert saved_session in out
        assert "train resnet50" in out
        assert "done" in out

    def test_show_session(self, saved_session: str, capsys: pytest.CaptureFixture[str]) -> None:
        sessions_cmd.show_session(saved_session)
        out = capsys.readouterr().out
        assert "train" in out and "resnet50" in out
        assert f"--from-session {saved_session}" in out

    def test_show_unknown(self) -> None:
        with pytest.raises(typer.Exit) as ei:
            sessions_cmd.show_session("ghost")
        assert ei.value.exit_code == 1

    def test_show_corrupted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "h3"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        d = home / ".local/share/computepilot/sessions"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("{not json")
        with pytest.raises(typer.Exit) as ei:
            sessions_cmd.show_session("bad")
        assert ei.value.exit_code == 1

    def test_clean_removes_old_only(self, saved_session: str) -> None:
        d = sessions_cmd._sessions_dir()
        old_file = d / "old000000.json"
        old_file.write_text(json.dumps({"id": "old000000"}))
        very_old = time.time() - 40 * 86400
        os.utime(old_file, (very_old, very_old))

        sessions_cmd.clean_sessions(days=30)

        assert not old_file.exists()
        assert (d / f"{saved_session}.json").exists()

    def test_clean_nothing_todo(self, saved_session: str) -> None:
        sessions_cmd.clean_sessions(days=30)


class TestWebUIApi:
    @pytest.fixture
    def api_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from computepilot.cli import webui

        home = tmp_path / "apihome"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        db = home / ".local/share/computepilot/state.db"
        store = StateStore(db)
        run = Run(id="r_api", workflow_id=uuid4(), workflow_sha256="s", status=RunStatus.RUNNING)
        store.create_run(run)
        store.transition_task("r_api", "t1", TaskStatus.SUCCEEDED, exit_code=0)
        store.record_event("r_api", "t1", "diagnosis", {"cause": "none"})
        store.close()
        monkeypatch.setattr(webui, "STATE_DB", db)
        return db

    def test_api_runs(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        client = TestClient(webui.app)
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert any(r["id"] == "r_api" for r in runs)

    def test_api_run_detail(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        client = TestClient(webui.app)
        data = client.get("/api/run/r_api").json()
        assert data["run"]["id"] == "r_api"
        assert data["tasks"][0]["task_id"] == "t1"
        assert len(data["events"]) >= 1

    def test_api_run_not_found(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        resp = TestClient(webui.app).get("/api/run/ghost")
        assert resp.status_code == 404

    def test_api_events_cursor(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        client = TestClient(webui.app)
        first = client.get("/api/run/r_api/events").json()
        assert first["cursor"] >= 1
        second = client.get(f"/api/run/r_api/events?after={first['cursor']}").json()
        assert second["events"] == []

    def test_api_events_unknown_run(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        resp = TestClient(webui.app).get("/api/run/ghost/events")
        assert resp.status_code == 404

    def test_run_page_has_events_section(self, api_db: Path) -> None:
        from fastapi.testclient import TestClient

        from computepilot.cli import webui

        resp = TestClient(webui.app).get("/run/r_api")
        assert "Events" in resp.text and "diagnosis" in resp.text
