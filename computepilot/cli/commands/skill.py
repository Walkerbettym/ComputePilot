"""computepilot skill — manage registered skills."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from computepilot.skills.base import SkillRegistry
from computepilot.skills.docker import docker_skill
from computepilot.skills.python import python_skill
from computepilot.skills.shell import shell_skill
from computepilot.skills.slurm import slurm_skill

console = Console()

_registry = SkillRegistry()
_registry.register(python_skill)
_registry.register(shell_skill)
_registry.register(slurm_skill)
_registry.register(docker_skill)


def list_skills() -> None:
    """List all registered skills."""
    skills = _registry.list_all()
    if not skills:
        console.print("[yellow]No skills registered.[/yellow]")
        return

    table = Table(title="Registered Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Description")
    table.add_column("Capabilities")

    for s in skills:
        caps = ", ".join(s.capabilities[:4])
        if len(s.capabilities) > 4:
            caps = f"{caps} …"
        table.add_row(s.name, s.version, s.description, caps)

    console.print(table)


def add_skill(path: str) -> None:
    """Load a skill from a YAML file and register it."""
    p = Path(path)
    if not p.exists():
        console.print(f"[red]✗ File not found: {path}[/red]")
        raise typer.Exit(2)

    skill = _registry.load_from_path(str(p))
    _registry.register(skill)
    msg = f"[green]✓[/green] Registered skill '[bold]{skill.name}[/bold]' ({skill.version})"
    console.print(msg)


skill_app = typer.Typer(help="Manage registered skills")


skill_app.command(name="list")(list_skills)
skill_app.command(name="add")(add_skill)
