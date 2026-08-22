"""cpilot status — show run status."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

import typer

from computepilot.cli.ui import console, print_run_detail, print_text
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
    live: bool = typer.Option(
        False, "--live", "-l", help="Live progress monitoring with ExecutionSentinel"
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Show status of a run, or list all runs. Use --live for progress."""
    conn = _get_db()

    if json_output:
        if run_id is None:
            rows_out = conn.execute(
                "SELECT id,status,executor,workflow_name,created_at FROM runs "
                "ORDER BY created_at DESC"
            ).fetchall()
            print_text(json.dumps({"runs": [dict(r) for r in rows_out]}, indent=2))
        else:
            try:
                payload = _run_payload(conn, run_id)
            except KeyError as exc:
                console.print(f"[red]❌ {exc.args[0]}[/red]")
                raise typer.Exit(1) from exc
            print_text(json.dumps(payload, indent=2))
        return

    if live:
        if run_id is None:
            console.print("[yellow]⚠ --live requires a RUN_ID[/yellow]")
            return
        _live_progress(conn, run_id)
        return

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


def _run_payload(conn: sqlite3.Connection, run_id: str) -> dict[str, object]:
    """Build the JSON-serializable detail for one run (mirrors /api/run/{id})."""
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(f"run '{run_id}' not found")
    tasks = [
        dict(t)
        for t in conn.execute(
            "SELECT task_id,status,attempt,exit_code,error FROM task_states WHERE run_id=?",
            (run_id,),
        ).fetchall()
    ]
    events = [
        dict(e)
        for e in conn.execute(
            "SELECT id,task_id,event,at,payload FROM task_events WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    ]
    try:
        cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    except json.JSONDecodeError:
        cfg = {}
    wf_cfg = cfg.get("workflow") if isinstance(cfg, dict) else {}
    return {
        "run": {
            "id": row["id"],
            "status": row["status"],
            "workflow_name": row["workflow_name"],
            "workflow_sha256": row["workflow_sha256"],
            "executor": row["executor"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "config": wf_cfg if isinstance(wf_cfg, dict) else {},
        },
        "tasks": tasks,
        "events": events,
    }


def _live_progress(conn: sqlite3.Connection, run_id: str) -> None:
    """Live progress via ExecutionSentinel — refresh every 2s."""
    import time

    from computepilot.runtime.sentinel import ExecutionSentinel
    from computepilot.runtime.state import StateStore

    row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    state_db = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    store = StateStore(state_db)
    sentinel = ExecutionSentinel(state=store)

    # Try to infer total tasks from config; if unavailable use completed count
    run_row = conn.execute("SELECT config_json FROM runs WHERE id = ?", (run_id,)).fetchone()
    total = 0
    if run_row:
        try:
            cfg = json.loads(run_row["config_json"])
            total = int(cfg.get("total_tasks", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            total = 0

    if total <= 0:
        # Fall back to the number of tasks already recorded for this run
        count_row = conn.execute(
            "SELECT COUNT(DISTINCT task_id) AS c FROM task_states WHERE run_id = ?", (run_id,)
        ).fetchone()
        total = int(count_row["c"]) if count_row else 0
    if total <= 0:
        # Last resort: watch with a generous total (we show what we know)
        total = 100

    sentinel.watch(run_id, total_tasks=total)
    console.print(f"[cyan]▶ Live monitoring run '{run_id}' (Ctrl-C to stop)[/cyan]")

    try:
        while True:
            report = sentinel.report_progress(run_id)
            if report is None:
                console.print(f"[yellow]⚠ No progress data for {run_id}[/yellow]")
                break

            bar_len = 30
            pct = report.pct / 100
            filled = int(bar_len * pct)
            bar = "█" * filled + "░" * (bar_len - filled)
            console.print(
                f"\r  [{bar}] {report.pct:.1f}% "
                f"({report.completed}/{report.total_tasks}) "
                f"{report.elapsed_seconds:.0f}s",
                end="",
            )

            if report.anomalies:
                console.print()
                for a in report.anomalies:
                    console.print(f"  [yellow]⚠ {a['type']}: {a['description']}[/yellow]")

            if report.completed + report.failed >= report.total_tasks:
                console.print()
                console.print(
                    "[green]✓ Run completed[/green]"
                    if report.failed == 0
                    else f"[red]✗ Run finished with {report.failed} failures[/red]"
                )
                break

            time.sleep(2)

    except KeyboardInterrupt:
        console.print()
        console.print("[yellow]Monitoring stopped by user[/yellow]")
    finally:
        sentinel.unwatch(run_id)


def _color(status: str) -> str:
    colors = {
        "created": "blue",
        "running": "cyan",
        "succeeded": "green",
        "failed": "red",
        "cancelled": "dim",
    }
    return colors.get(status, "white")
