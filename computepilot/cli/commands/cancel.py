"""cpilot cancel — cancel a running run."""

from __future__ import annotations

import contextlib
import os
import signal
import sqlite3
import time
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


def _latest_pids(conn: sqlite3.Connection, run_id: str) -> dict[str, int]:
    """Map RUNNING task_id → most recent recorded process pid."""
    pids: dict[str, int] = {}
    rows = conn.execute(
        "SELECT t.task_id, e.payload FROM task_states t "
        "JOIN task_events e ON e.run_id = t.run_id AND e.task_id = t.task_id "
        "WHERE t.run_id = ? AND t.status = 'running' AND e.event = 'process_started' "
        "ORDER BY e.id DESC",
        (run_id,),
    ).fetchall()
    for r in rows:
        tid = r["task_id"]
        if tid in pids:
            continue
        try:
            import json

            payload = json.loads(r["payload"]) if r["payload"] else {}
            pid = payload.get("pid")
            if isinstance(pid, int):
                pids[tid] = pid
        except (ValueError, TypeError):
            continue
    return pids


def _terminate(pid: int) -> bool:
    """SIGTERM a pid, escalating to SIGKILL after a short grace period."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, 0)
            time.sleep(0.05)
            continue
        return True
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    return True


def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel", metavar="RUN_ID"),
    kill: bool = typer.Option(False, "--kill", "-k", help="Also terminate running task processes"),
) -> None:
    """Cancel a running run by setting its status to CANCELLED."""
    conn = _get_db()

    row = conn.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    current_status = row["status"]
    terminal_states = {
        RunStatus.SUCCEEDED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    }

    if current_status in terminal_states:
        console.print(
            f"[yellow]⚠ Run '{run_id}' is already {current_status} — nothing to cancel.[/yellow]"
        )
        raise typer.Exit(0)

    killed = 0
    if kill:
        for task_id, pid in _latest_pids(conn, run_id).items():
            if _terminate(pid):
                killed += 1
                console.print(f"[cyan]✓ Terminated task '{task_id}' (pid {pid})[/cyan]")
            else:
                console.print(f"[dim]  task '{task_id}' (pid {pid}) already gone[/dim]")
        if not killed:
            console.print("[dim]No running processes to kill.[/dim]")

    conn.execute("UPDATE runs SET status = ? WHERE id = ?", (RunStatus.CANCELLED.value, run_id))
    conn.commit()
    conn.close()

    suffix = f" ({killed} process(es) terminated)" if kill and killed else ""
    console.print(f"[green]✓ Run '{run_id}' cancelled.{suffix}[/green]")
