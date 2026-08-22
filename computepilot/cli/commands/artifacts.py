"""cpilot artifacts — list/export artifacts for a given run."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import typer

from computepilot.artifacts.store import ArtifactStore
from computepilot.cli.ui import console, print_text
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
    get: bool = typer.Option(False, "--get", "-g", help="Export artifact files"),
    task_id: str | None = typer.Option(None, "--task", "-t", help="Only this task's artifacts"),
    output: str = typer.Option(
        "./exported_artifacts", "--output", "-o", help="Destination dir for --get"
    ),
) -> None:
    """List artifacts for a run; with --get, export files and verify checksums."""
    store = _get_store()
    if store is None:
        raise typer.Exit(0)

    rows = [a for a in store.list_for_run(run_id) if task_id is None or a["task_id"] == task_id]

    if get:
        _export(rows, Path(output))
        return

    if not rows:
        console.print(f"[dim]No artifacts found for run '{run_id}'.[/dim]")
        return

    console.print(f"[bold]Artifacts for run {run_id}:[/bold]")
    for art in rows:
        console.print(f"  {art['id'][:12]}  {art['type']:<12}  {art['size']:>8} B  {art['path']}")

    # Also output JSON for scripting
    print_text(json.dumps(rows, indent=2))


def _export(rows: list[dict[str, object]], dest: Path) -> None:
    """Copy artifact files to *dest*, verifying registered checksums."""
    if not rows:
        console.print("[dim]No matching artifacts to export.[/dim]")
        return
    dest.mkdir(parents=True, exist_ok=True)

    exported, mismatched, missing = 0, 0, 0
    for art in rows:
        src = Path(str(art["path"]))
        if not src.exists():
            console.print(f"[yellow]⚠ missing on disk: {src}[/yellow]")
            missing += 1
            continue
        target = dest / src.name
        shutil.copy2(src, target)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != art["checksum"]:
            console.print(
                f"[red]⚠ checksum mismatch for {src.name}: "
                f"registered {str(art['checksum'])[:12]}… got {actual[:12]}…[/red]"
            )
            mismatched += 1
        else:
            exported += 1

    console.print(
        f"[green]✓ Exported {exported} artifact(s) to {dest}[/green]"
        + (f" [yellow]({missing} missing)[/yellow]" if missing else "")
        + (f" [red]({mismatched} corrupted)[/red]" if mismatched else "")
    )
    if mismatched:
        raise typer.Exit(1)
