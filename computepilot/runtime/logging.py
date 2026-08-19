"""Structured JSON logging for workflow runs.

Produces a run.log file with structured JSON entries for every
event during a workflow execution.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def log_event(
    run_dir: str | Path,
    event: str,
    task_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a structured JSON event to *run_dir*/run.log.

    Each event is a single JSON line.  The log file is created if it
    does not exist.
    """
    log_path = Path(run_dir) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry: dict[str, Any] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "event": event,
    }
    if task_id is not None:
        entry["task_id"] = task_id
    if payload:
        entry["payload"] = payload

    with log_path.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_events(run_dir: str | Path) -> list[dict[str, Any]]:
    """Read all JSON events from *run_dir*/run.log.

    Returns an empty list if the log file does not exist or is malformed.
    """
    log_path = Path(run_dir) / "run.log"
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
