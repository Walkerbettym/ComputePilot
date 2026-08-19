"""computepilot cancel — cancel a running run."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import typer

from computepilot.cli.ui import console
from computepilot.models.run import RunStatus


def _get_db() -> sqlite3.Connection:
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[red]❌ No runs found (state database does not exist)[/red]")
        raise typer.Exit(0)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel", metavar="RUN_ID"),
) -> None:
    """Cancel a running run by setting its status to CANCELLED."""
    conn = _get_db()

    row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    current_status = row["status"]
    terminal_states = {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}

    if current_status in terminal_states:
        console.print(
            f"[yellow]⚠ Run '{run_id}' is already {current_status} — nothing to cancel.[/yellow]"
        )
        raise typer.Exit(0)

    conn.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.CANCELLED.value, run_id))
    conn.commit()
    conn.close()

    console.print(f"[green]✓ Run '{run_id}' cancelled.[/green]")
