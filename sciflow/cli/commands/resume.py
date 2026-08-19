"""sciflow resume — resume a previously-started run from its last checkpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from sciflow.cli.ui import console
from sciflow.executors.local import LocalExecutor
from sciflow.runtime.engine import Engine
from sciflow.runtime.state import StateStore
from sciflow.workflow.schema import load_workflow


def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume", metavar="RUN_ID"),
    workflow_path: str = typer.Option(
        "", "--workflow", "-w", help="Path to workflow.yaml (default: auto-detect)"
    ),
    executor: str = typer.Option("local", "--executor", "-e", help="Executor backend"),
    max_concurrency: int = typer.Option(4, "--max-concurrency", "-j", help="Max concurrent tasks"),
) -> None:
    """Resume a previously-started run, skipping completed tasks."""
    # Open the state store
    state_dir = Path.home() / ".local" / "share" / "sciflow"
    state_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(state_dir / "state.db")

    # Verify the run exists
    run_data = store.get_run(run_id)
    if run_data is None:
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(1)

    # Determine the workflow path
    if workflow_path:
        wf_path = Path(workflow_path)
    else:
        # Try to load from the original run directory convention
        wf_path = Path.cwd() / "workflow.yaml"
        if not wf_path.exists():
            console.print(
                "[red]❌ Could not locate workflow.yaml. Specify with --workflow / -w[/red]"
            )
            raise typer.Exit(2)

    if not wf_path.exists():
        console.print(f"[red]❌ workflow not found: {wf_path}[/red]")
        raise typer.Exit(2)

    wf = load_workflow(wf_path)

    exe = LocalExecutor()
    engine = Engine(state=store, executor=exe, max_concurrency=max_concurrency)

    console.print(f"[cyan]▶ Resuming run '{run_id}'[/cyan]")

    try:
        result = asyncio.run(
            engine.resume(
                workflow=wf,
                run_id=run_id,
                run_dir=wf_path.parent,
                env={},
            )
        )
    except Exception as exc:
        console.print(f"[red]✗ Resume failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    if result.status.value == "succeeded":
        console.print("[green]✓ Run resumed and completed successfully[/green]")
    else:
        console.print(f"[red]✗ Run resumed but failed: {result.status.value}[/red]")
        raise typer.Exit(1)
