"""cpilot logs — show task logs for a run."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import typer

from computepilot.cli.ui import console, print_task_logs, print_text


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
    follow: bool = typer.Option(
        False, "--follow", "-F", help="Keep the stream open and print new events as they arrive"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output events as a JSON array"),
    limit: int = typer.Option(500, "--limit", "-l", help="Max events with --json (from newest)"),
) -> None:
    """Show task event logs for a run (optionally follow new events)."""
    conn = _get_db()

    # Verify run exists
    run_row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
    if run_row is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    rows = conn.execute(
        "SELECT id, task_id, event, at, payload FROM task_events WHERE run_id = ? ORDER BY id ASC",
        (run_id,),
    ).fetchall()

    if json_output:
        selected = [_row_to_event(r) for r in rows if task_id is None or r["task_id"] == task_id]
        print_text(json.dumps(selected[-limit:], indent=2, default=str))
        return

    events = [_row_to_event(r) for r in rows]
    print_task_logs(events, task_id=task_id, tail=tail)

    if not follow:
        return

    console.print("[cyan]▶ Following new events (Ctrl-C to stop)[/cyan]")
    last_id = max((r["id"] for r in rows), default=0)
    try:
        import time

        while True:
            time.sleep(1)
            fresh = conn.execute(
                "SELECT id, task_id, event, at, payload FROM task_events "
                "WHERE run_id = ? AND id > ? ORDER BY id ASC",
                (run_id, last_id),
            ).fetchall()
            for r in fresh:
                entry = _row_to_event(r)
                at = entry.get("at", "")[:19]
                tid = entry.get("task_id", "-")
                event = entry.get("event", "-")
                if task_id is not None and tid != task_id:
                    continue
                console.print(f"  [dim]{at}[/dim] [bold]{tid}[/bold] {event}")
            if fresh:
                last_id = max(last_id, max(r["id"] for r in fresh))
    except KeyboardInterrupt:
        conn.close()
        console.print()
        console.print("[yellow]Follow stopped by user[/yellow]")


def _row_to_event(r: sqlite3.Row) -> dict[str, Any]:
    """Convert a task_events row into a log-entry dict."""
    entry: dict[str, object] = {"task_id": r["task_id"], "event": r["event"], "at": r["at"]}
    if r["payload"]:
        try:
            entry["payload"] = json.loads(r["payload"])
        except (json.JSONDecodeError, TypeError):
            entry["payload"] = r["payload"]
    return entry
