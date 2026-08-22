"""Integration-style tests for cpilot logs --follow."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from computepilot.cli.commands import logs as logs_cmd
from computepilot.models.run import Run, TaskStatus
from computepilot.runtime.state import StateStore


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    p = home / ".local" / "share" / "computepilot" / "state.db"
    store = StateStore(p)
    store.create_run(
        Run(id="r_follow", workflow_id=__import__("uuid").uuid4(), workflow_sha256="x")
    )
    store.transition_task("r_follow", "t1", TaskStatus.SUCCEEDED, exit_code=0)
    store.close()
    return p


def test_follow_captures_new_events(
    db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def producer() -> None:
        time.sleep(1.5)
        s = StateStore(db)
        s.record_event("r_follow", "t2", "diagnosis", {"cause": "OOM"})
        s.close()

    t = threading.Thread(target=producer)
    t.start()

    import signal

    def alarm(sig: int, frame: object) -> None:
        raise KeyboardInterrupt

    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(5)
    try:
        logs_cmd.logs("r_follow", task_id=None, tail=50, follow=True, json_output=False, limit=500)
    except KeyboardInterrupt:
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        t.join()

    out = capsys.readouterr().out
    assert "Following new events" in out
    assert "diagnosis" in out
