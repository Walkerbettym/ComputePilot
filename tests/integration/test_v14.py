"""Tests for v1.4: cancel --kill, busy_timeout, failure webhooks."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from computepilot.cli.commands import cancel as cancel_cmd
from computepilot.executors.local import LocalExecutor
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore

# -- busy_timeout -----------------------------------------------------------------


def test_busy_timeout_pragma(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s.db")
    row = store._conn.execute("PRAGMA busy_timeout").fetchone()
    assert row[0] == 5000
    store.close()


def test_concurrent_writers_do_not_raise(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    StateStore(db).close()  # create schema first
    errors: list[str] = []

    def writer(tag: str) -> None:
        try:
            store = StateStore(db)
            for i in range(20):
                store.create_run(
                    Run(
                        id=f"{tag}_{i}",
                        workflow_id=uuid4(),
                        workflow_sha256="x",
                        status=RunStatus.SUCCEEDED,
                    )
                )
            store.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{tag}: {exc}")

    threads = [threading.Thread(target=writer, args=(t,)) for t in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    assert n == 60


# -- process_started pid events -----------------------------------------------------


def test_engine_records_process_pid(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "s.db")
    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=1)
    from computepilot.models.workflow import Task, Workflow

    wf = Workflow(name="pidwf", tasks=[Task(id="hi", command="echo hi")])
    import asyncio

    run = asyncio.run(engine.run(wf, run_id="r_pid", run_dir=str(tmp_path)))
    assert run.status.value == "succeeded"
    rows = store._conn.execute(
        "SELECT payload FROM task_events WHERE run_id='r_pid' AND event='process_started'"
    ).fetchall()
    store.close()
    assert rows and isinstance(json.loads(rows[0]["payload"])["pid"], int)


# -- cancel --kill --------------------------------------------------------------------


class TestCancelKill:
    @pytest.fixture
    def running_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[str, int, subprocess.Popen[bytes]]:
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)
        db = home / ".local/share/computepilot/state.db"
        db.parent.mkdir(parents=True)

        proc = subprocess.Popen(["sleep", "30"])
        store = StateStore(db)
        store.create_run(
            Run(id="r_kill", workflow_id=uuid4(), workflow_sha256="x", status=RunStatus.RUNNING)
        )
        store.update_run_status("r_kill", RunStatus.RUNNING)
        store.transition_task("r_kill", "sleeper", TaskStatus.RUNNING)
        store.record_event("r_kill", "sleeper", "process_started", {"pid": proc.pid})
        store.close()

        yield "r_kill", proc.pid, proc
        if proc.poll() is None:
            proc.kill()

    def test_kill_terminates_process(
        self, running_env: tuple[str, int, subprocess.Popen[bytes]]
    ) -> None:
        run_id, pid, proc = running_env
        time.sleep(0.05)
        cancel_cmd.cancel(run_id, kill=True)

        assert proc.wait(timeout=3) is not None or proc.poll() is not None

        conn = sqlite3.connect(str(Path.home() / ".local/share/computepilot/state.db"))
        status = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.close()
        assert status == "cancelled"

    def test_without_kill_flag_spares_process(
        self, running_env: tuple[str, int, subprocess.Popen[bytes]]
    ) -> None:
        run_id, pid, proc = running_env
        time.sleep(0.05)
        cancel_cmd.cancel(run_id, kill=False)
        os.kill(pid, 0)  # still alive
        conn = sqlite3.connect(str(Path.home() / ".local/share/computepilot/state.db"))
        status = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        conn.close()
        assert status == "cancelled"


# -- failure webhook -------------------------------------------------------------------


class _Hook(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()


@pytest.fixture
def hook_server() -> str:
    _Hook.received.clear()
    server = HTTPServer(("127.0.0.1", 0), _Hook)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/hook"
    server.shutdown()


def test_failure_webhook_fires(tmp_path: Path, monkeypatch, hook_server: str) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "wf.yaml").write_text(
        f"name: notify_wf\n"
        f"notifications:\n"
        f"  on_failed:\n"
        f"    url: {hook_server}\n"
        f"tasks:\n"
        f"  - id: boom\n    command: exit 2\n    type: shell\n"
    )
    from computepilot import api

    state = tmp_path / "state"
    monkeypatch.setattr(api, "DEFAULT_STATE_DIR", state)
    run = api.run("wf.yaml")
    assert run.status.value == "failed"

    deadline = time.monotonic() + 5
    while not _Hook.received and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _Hook.received, "webhook never fired"
    body = _Hook.received[0]
    assert body["event"] == "run_failed"
    assert body["run_id"] == run.id
    assert body["workflow"] == "notify_wf"


def test_success_webhook_not_sent_when_only_on_failed(
    tmp_path: Path, monkeypatch, hook_server: str
) -> None:
    work = tmp_path / "w2"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "ok.yaml").write_text(
        f"name: ok_wf\nnotifications:\n  on_failed:\n    url: {hook_server}\n"
        "tasks:\n  - id: fine\n    command: echo ok\n    type: shell\n"
    )
    from computepilot import api

    monkeypatch.setattr(api, "DEFAULT_STATE_DIR", tmp_path / "state")
    api.run("ok.yaml")
    time.sleep(0.3)
    assert _Hook.received == []


def test_unreachable_webhook_is_silent(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "w3"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "bad_url.yaml").write_text(
        "name: bad_hook\n"
        "notifications:\n  on_failed:\n    url: http://127.0.0.1:1/nope\n    timeout: 1\n"
        "tasks:\n  - id: boom\n    command: exit 1\n    type: shell\n"
    )
    from computepilot import api

    monkeypatch.setattr(api, "DEFAULT_STATE_DIR", tmp_path / "state")
    run = api.run("bad_url.yaml")
    assert run.status.value == "failed"


# silence unused-import linters for signal (kept for clarity of intent)
_ = signal.SIGTERM
