"""sciflow run — execute a workflow."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer

from sciflow.cli.ui import console
from sciflow.executors.local import LocalExecutor
from sciflow.runtime.engine import Engine
from sciflow.runtime.state import StateStore
from sciflow.workflow.schema import load_workflow
from sciflow.workflow.validator import validate


def run(
    workflow_path: str = typer.Argument(
        ..., help="Path to workflow.yaml", metavar="WORKFLOW"
    ),
    executor: str = typer.Option("local", "--executor", "-e", help="Executor backend"),
    max_concurrency: int = typer.Option(
        4, "--max-concurrency", "-j", help="Max concurrent tasks"
    ),
    approve: bool = typer.Option(
        False, "--approve", "-y", help="Auto-approve (no confirmation prompt)"
    ),
) -> None:
    """Execute a workflow."""
    path = Path(workflow_path)
    if not path.exists():
        console.print(f"[red]❌ workflow not found: {path}[/red]")
        raise typer.Exit(2)

    # Load and validate
    wf = load_workflow(path)
    report = validate(wf)
    if not report.passed:
        console.print("[red]❌ Workflow validation failed:[/red]")
        from sciflow.cli.ui import print_validation_report

        print_validation_report(report, workflow_path)
        raise typer.Exit(2)

    # Confirmation prompt
    if not approve:
        console.print(f"[bold]Workflow:[/bold] {wf.name}")
        console.print(f"[bold]Tasks:[/bold] {len(wf.tasks)}")
        confirm = typer.confirm("Proceed with execution?", default=True)
        if not confirm:
            console.print("[yellow]Aborted by user[/yellow]")
            raise typer.Exit(0)

    # Prepare state store and executor
    state_dir = Path.home() / ".local" / "share" / "sciflow"
    state_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(state_dir / "state.db")

    run_id = f"run_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_dir = path.parent / "runs" / run_id

    exe = LocalExecutor()
    engine = Engine(state=store, executor=exe, max_concurrency=max_concurrency)

    console.print(f"[cyan]▶ Running workflow '{wf.name}' (run_id={run_id})[/cyan]")

    try:
        result = asyncio.run(
            engine.run(
                workflow=wf,
                run_id=run_id,
                config={},
                run_dir=run_dir,
                env={},
            )
        )
    except Exception as exc:
        console.print(f"[red]✗ Run failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    if result.status.value == "succeeded":
        console.print("[green]✓ Run completed successfully[/green]")
    else:
        console.print(f"[red]✗ Run failed: {result.status.value}[/red]")
        raise typer.Exit(1)
