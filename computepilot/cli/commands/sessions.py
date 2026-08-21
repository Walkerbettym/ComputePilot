"""cpilot sessions — inspect and manage saved Conductor sessions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from computepilot.cli.commands.run import _sessions_dir

console = Console()


def _load(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def list_sessions_cmd() -> None:
    """List all saved interactive sessions."""
    d = _sessions_dir()
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        console.print("[dim]No saved sessions.[/dim]")
        console.print('[dim]Create one with: cpilot run --interactive "..."[/dim]')
        return

    table = Table(title="Saved Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Phase")
    table.add_column("Intent", style="bold")
    table.add_column("Created", style="dim")

    for f in files:
        data = _load(f)
        intent = data.get("current_intent")
        if isinstance(intent, dict):
            summary = f"{intent.get('verb', '?')} {intent.get('target', '?')}"
        else:
            summary = "-"
        created = str(data.get("created_at", ""))[:19].replace("T", " ") or f.name
        table.add_row(f.stem, str(data.get("phase", "?")), summary, created)
    console.print(table)


def show_session(session_id: str) -> None:
    """Show the conversation history and extracted intent of a session."""
    path = _sessions_dir() / f"{session_id}.json"
    if not path.exists():
        console.print(f"[red]❌ Session not found: {session_id}[/red]")
        raise typer.Exit(1)

    data = _load(path)
    if not data:
        console.print(f"[red]❌ Corrupted session file: {path}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Session[/bold] [cyan]{session_id}[/cyan]  "
        f"phase=[yellow]{data.get('phase', '?')}[/yellow]"
    )
    history = data.get("history") or []
    if isinstance(history, list):
        console.print()
        for entry in history:
            role = entry.get("role", "?") if isinstance(entry, dict) else "?"
            content = entry.get("content", "") if isinstance(entry, dict) else ""
            style = "green" if role == "user" else "white"
            console.print(f"  [{style}]{role}[/{style}]: {content[:120]}")

    intent = data.get("current_intent")
    if isinstance(intent, dict):
        console.print()
        console.print("[bold]Intent:[/bold]")
        console.print(f"  verb:     {intent.get('verb', '-')}")
        console.print(f"  target:   {intent.get('target', '-')}")
        params = intent.get("parameters") or {}
        for k, v in params.items():
            console.print(f"  {k}: {v}")
        resources = intent.get("resources") or {}
        if resources:
            console.print(f"  resources: {resources}")
    else:
        console.print("[yellow]No workflow plan in this session yet.[/yellow]")

    console.print()
    console.print(f"[dim]Resume: cpilot run --from-session {session_id}[/dim]")


def clean_sessions(
    days: int = typer.Option(30, "--days", "-d", help="Delete sessions older than N days"),
) -> None:
    """Delete saved sessions older than the given number of days."""
    cutoff = datetime.now(tz=UTC).timestamp() - days * 86400
    d = _sessions_dir()
    removed = 0
    for f in d.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    console.print(f"[green]✓ Removed {removed} session(s) older than {days} day(s)[/green]")


sessions_app = typer.Typer(help="Inspect and manage saved interactive sessions")
sessions_app.command(name="list")(list_sessions_cmd)
sessions_app.command(name="show")(show_session)
sessions_app.command(name="clean")(clean_sessions)
