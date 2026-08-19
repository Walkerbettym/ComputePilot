"""Tests for structured JSON logging."""

from __future__ import annotations

from pathlib import Path

from computepilot.runtime.logging import log_event, read_events


def test_log_event_creates_file(tmp_path: Path) -> None:
    """log_event writes a JSON line to run.log."""
    log_event(tmp_path, event="run_started", task_id="t1", payload={"k": 1})
    assert (tmp_path / "run.log").exists()

    events = read_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event"] == "run_started"
    assert events[0]["task_id"] == "t1"
    assert events[0]["payload"] == {"k": 1}
    assert "timestamp" in events[0]


def test_log_event_append(tmp_path: Path) -> None:
    """Multiple events are appended as separate JSON lines."""
    log_event(tmp_path, event="a")
    log_event(tmp_path, event="b", task_id="t2")
    log_event(tmp_path, event="c", payload={"n": 3})

    events = read_events(tmp_path)
    assert [e["event"] for e in events] == ["a", "b", "c"]
    assert events[1]["task_id"] == "t2"
    assert events[2]["payload"] == {"n": 3}


def test_read_events_empty(tmp_path: Path) -> None:
    """Reading from a run_dir without a log returns empty list."""
    assert read_events(tmp_path) == []


def test_read_events_skips_invalid(tmp_path: Path) -> None:
    """Malformed lines are skipped while valid ones are read."""
    (tmp_path / "run.log").write_text('{"event": "ok"}\nnot-json-at-all\n{"event": "also-good"}\n')

    events = read_events(tmp_path)
    assert len(events) == 2
    assert events[0]["event"] == "ok"
    assert events[1]["event"] == "also-good"


def test_log_event_nested_payload(tmp_path: Path) -> None:
    """Complex payloads (timedelta etc.) serialize via default=str."""
    from datetime import timedelta

    log_event(
        tmp_path,
        event="timeout",
        task_id="t1",
        payload={"delay": timedelta(seconds=30)},
    )
    events = read_events(tmp_path)
    assert events[0]["payload"]["delay"] == "0:00:30"
