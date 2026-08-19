"""computepilot status — show run status."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

import typer

from computepilot.cli.ui import console, print_run_detail
from computepilot.models.run import Run, RunStatus


def _get_db() -> sqlite3.Connection:
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[red]❌ No runs found (state database does not exist)[/red]")
        raise typer.Exit(0)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def status(
    run_id: str | None = typer.Argument(
        None, help="Run ID to inspect (omit to list all runs)", metavar="RUN_ID"
    ),
) -> None:
    """Show status of a run, or list all runs."""
    conn = _get_db()

    if run_id is None:
        rows = conn.execute(
            "SELECT id, status, created_at FROM runs ORDER BY created_at DESC"
        ).fetchall()
        if not rows:
            console.print("[dim]No runs recorded yet.[/dim]")
            return
        console.print("[bold]Recent runs:[/bold]")
        for row in rows:
            status_val = row["status"]
            created = row["created_at"][:19] if row["created_at"] else "-"
            console.print(f"  {row['id']} — [{_color(status_val)}]{status_val}[/] ({created})")
        return

    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    run = Run(
        id=row["id"],
        workflow_id=UUID(row["workflow_id"]),
        workflow_sha256=row["workflow_sha256"],
        status=RunStatus(row["status"]),
        executor=row["executor"],
        config=json.loads(row["config_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
    )

    # Get task states
    task_rows = conn.execute(
        "SELECT task_id, status, exit_code, error FROM task_states WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    tasks = [dict(r) for r in task_rows]

    print_run_detail(run, tasks)


def _color(status: str) -> str:
    colors = {
        "created": "blue",
        "running": "cyan",
        "succeeded": "green",
        "failed": "red",
        "cancelled": "dim",
    }
    return colors.get(status, "white")
