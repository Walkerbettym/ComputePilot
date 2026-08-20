"""cpilot logs — show task logs for a run."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import typer

from computepilot.cli.ui import console, print_task_logs


def _get_db() -> sqlite3.Connection:
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[red]❌ No runs found (state database does not exist)[/red]")
        raise typer.Exit(0)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def logs(
    run_id: str = typer.Argument(..., help="Run ID", metavar="RUN_ID"),
    task_id: str | None = typer.Option(None, "--task", "-t", help="Filter by task ID"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
) -> None:
    """Show task event logs for a run."""
    conn = _get_db()

    # Verify run exists
    run_row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
    if run_row is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    rows = conn.execute(
        "SELECT task_id, event, at, payload FROM task_events WHERE run_id = ? ORDER BY id ASC",
        (run_id,),
    ).fetchall()

    events = []
    for r in rows:
        entry = {"task_id": r["task_id"], "event": r["event"], "at": r["at"]}
        if r["payload"]:
            try:
                entry["payload"] = json.loads(r["payload"])
            except (json.JSONDecodeError, TypeError):
                entry["payload"] = r["payload"]
        events.append(entry)

    print_task_logs(events, task_id=task_id, tail=tail)
