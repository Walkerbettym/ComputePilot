"""computepilot artifacts — list artifacts for a given run."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from computepilot.artifacts.store import ArtifactStore
from computepilot.cli.ui import console
from computepilot.runtime.state import StateStore


def _get_store() -> ArtifactStore | None:
    db_path = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db_path.exists():
        console.print("[red]❌ No runs found (state database does not exist)[/red]")
        return None
    state = StateStore(db_path)
    return ArtifactStore(state)


def artifacts(
    run_id: str = typer.Argument(..., help="Run ID to inspect", metavar="RUN_ID"),
) -> None:
    """List artifacts registered for a run."""
    store = _get_store()
    if store is None:
        raise typer.Exit(0)

    artifacts_list = store.list_for_run(run_id)
    if not artifacts_list:
        console.print(f"[dim]No artifacts found for run '{run_id}'.[/dim]")
        return

    console.print(f"[bold]Artifacts for run {run_id}:[/bold]")
    for art in artifacts_list:
        console.print(f"  {art['id'][:12]}  {art['type']:<12}  {art['size']:>8} B  {art['path']}")

    # Also output JSON for scripting
    console.print(json.dumps(artifacts_list, indent=2))
