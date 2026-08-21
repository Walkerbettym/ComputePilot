"""cpilot runs — manage run history (list/clean)."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from computepilot.models.run import RunStatus

console = Console()

_TERMINAL = (
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
)


def _open_db() -> sqlite3.Connection:
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[dim]No state database.[/dim]")
        raise typer.Exit(0)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def list_runs(limit: int = typer.Option(20, "--limit", "-n", help="Max rows")) -> None:
    """List recent runs."""
    conn = _open_db()
    rows = conn.execute(
        "SELECT id,status,executor,created_at FROM runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    if not rows:
        console.print("[dim]No runs recorded yet.[/dim]")
        return
    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Status")
    table.add_column("Executor")
    table.add_column("Created", style="dim")
    for r in rows:
        table.add_row(r["id"], r["status"], r["executor"], str(r["created_at"])[:19])
    console.print(table)


def clean_runs(
    days: int = typer.Option(30, "--days", "-d", help="Delete terminal runs older than N days"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
) -> None:
    """Delete old terminal-state runs: DB rows in all five tables plus run dirs."""
    cutoff = (datetime.now(tz=UTC) - timedelta(days=days)).isoformat()
    conn = _open_db()
    rows = conn.execute(
        "SELECT id FROM runs WHERE status IN (?,?,?) AND created_at < ?",
        (*_TERMINAL, cutoff),
    ).fetchall()
    run_ids = [r["id"] for r in rows]

    if not run_ids:
        console.print(f"[dim]No terminal runs older than {days} day(s).[/dim]")
        conn.close()
        return

    if dry_run:
        console.print(f"[yellow]Would delete {len(run_ids)} run(s):[/yellow]")
        for rid in run_ids:
            console.print(f"  {rid}")
        conn.close()
        return

    placeholders = ",".join("?" * len(run_ids))
    for sql in (
        f"DELETE FROM task_states WHERE run_id IN ({placeholders})",
        f"DELETE FROM task_events WHERE run_id IN ({placeholders})",
        f"DELETE FROM artifacts WHERE run_id IN ({placeholders})",
        f"DELETE FROM approvals WHERE run_id IN ({placeholders})",
        f"DELETE FROM runs WHERE id IN ({placeholders})",
    ):
        conn.execute(sql, run_ids)
    conn.commit()
    conn.close()

    removed_dirs = 0
    runs_root = Path.cwd() / "runs"
    if runs_root.exists():
        for rid in run_ids:
            run_dir = runs_root / rid
            if run_dir.is_dir():
                shutil.rmtree(run_dir, ignore_errors=True)
                removed_dirs += 1

    console.print(
        f"[green]✓ Deleted {len(run_ids)} run(s) "
        f"({removed_dirs} run director(y/ies) under {runs_root})[/green]"
    )


runs_app = typer.Typer(help="Manage run history")
runs_app.command(name="list")(list_runs)
runs_app.command(name="clean")(clean_runs)
