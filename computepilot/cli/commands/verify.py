"""cpilot verify — compare two runs for reproducibility."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import typer
from rich.table import Table

from computepilot.cli.ui import console as ui_console

console = ui_console


def _artifact_index(arts: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Group artifact checksums by (task_id, type); run dirs differ across runs."""
    idx: dict[tuple[str, str], list[str]] = {}
    for x in arts:
        idx.setdefault((str(x["task_id"]), str(x["type"])), []).append(str(x["checksum"]))
    return {k: sorted(v) for k, v in idx.items()}


def _digests(checksums: list[str] | None) -> str:
    if not checksums:
        return "missing"
    return ",".join(c[:12] for c in checksums)


def _load_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    tasks = [
        dict(t)
        for t in conn.execute(
            "SELECT task_id,status,exit_code FROM task_states WHERE run_id=? ORDER BY task_id",
            (run_id,),
        ).fetchall()
    ]
    arts = [
        dict(a)
        for a in conn.execute(
            "SELECT task_id,path,checksum,size,type FROM artifacts WHERE run_id=? ORDER BY path",
            (run_id,),
        ).fetchall()
    ]
    return {
        "id": row["id"],
        "workflow_sha256": row["workflow_sha256"],
        "status": row["status"],
        "tasks": tasks,
        "artifacts": arts,
    }


def verify(
    run_a: str = typer.Argument(..., metavar="RUN_A"),
    run_b: str = typer.Argument(..., metavar="RUN_B"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Compare two runs: workflow hash, task outcomes, and artifact checksums.

    Exit codes: 0 identical (reproducible), 1 differences found, 2 error.
    """
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[red]❌ No state database[/red]")
        raise typer.Exit(2)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    a = _load_run(conn, run_a)
    b = _load_run(conn, run_b)
    conn.close()

    if a is None:
        console.print(f"[red]❌ Run '{run_a}' not found[/red]")
        raise typer.Exit(2)
    if b is None:
        console.print(f"[red]❌ Run '{run_b}' not found[/red]")
        raise typer.Exit(2)

    checks: list[dict[str, Any]] = []

    wf_match = a["workflow_sha256"] == b["workflow_sha256"]
    checks.append(
        {
            "category": "workflow",
            "detail": "sha256",
            "a": a["workflow_sha256"][:16],
            "b": b["workflow_sha256"][:16],
            "match": wf_match,
        }
    )

    ta = {t["task_id"]: (t["status"], t["exit_code"]) for t in a["tasks"]}
    tb = {t["task_id"]: (t["status"], t["exit_code"]) for t in b["tasks"]}
    for tid in sorted(set(ta) | set(tb)):
        sa, sb = ta.get(tid), tb.get(tid)
        checks.append(
            {
                "category": "task",
                "detail": tid,
                "a": f"{sa[0]}({sa[1]})" if sa else "missing",
                "b": f"{sb[0]}({sb[1]})" if sb else "missing",
                "match": sa == sb,
            }
        )

    ia = _artifact_index(a["artifacts"])
    ib = _artifact_index(b["artifacts"])
    for key in sorted(set(ia) | set(ib), key=str):
        ca, cb = ia.get(key), ib.get(key)
        checks.append(
            {
                "category": "artifact",
                "detail": f"{key[0]}:{key[1]}",
                "a": _digests(ca),
                "b": _digests(cb),
                "match": ca == cb,
            }
        )

    identical = all(c["match"] for c in checks)

    if json_output:
        payload = {
            "run_a": run_a,
            "run_b": run_b,
            "reproducible": identical,
            "checks": checks,
        }
        console.print(json.dumps(payload, indent=2), markup=False)
    else:
        table = Table(title=f"Verify: {run_a}  vs  {run_b}")
        table.add_column("Category", style="cyan")
        table.add_column("Item")
        table.add_column("A")
        table.add_column("B")
        table.add_column("Match")
        for c in checks:
            table.add_row(
                c["category"],
                str(c["detail"]),
                str(c["a"]),
                str(c["b"]),
                "[green]✓[/green]" if c["match"] else "[red]✗[/red]",
            )
        console.print(table)
        verdict = "[green]✓ REPRODUCIBLE[/green]" if identical else "[red]✗ DIFFERENCES FOUND[/red]"
        console.print(verdict)

    raise typer.Exit(0 if identical else 1)
