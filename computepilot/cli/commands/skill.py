"""cpilot skill — manage registered skills."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from computepilot.cli.ui import print_text
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


def show_skill(name: str) -> None:
    """Show a skill's full definition as YAML."""
    import yaml as _yaml

    skill = _registry.get(name)
    if skill is None:
        console.print(f"[red]✗ Skill not found: {name}[/red]")
        available = ", ".join(s.name for s in _registry.list_all())
        console.print(f"[dim]Available: {available}[/dim]")
        raise typer.Exit(1)
    print_text(_yaml.dump(skill.model_dump(mode="json"), sort_keys=False))


SKILL_TEMPLATE = """\
name: {name}
version: 0.1.0
description: "TODO: describe the domain capability"
capabilities: []
constraints:
  required_commands: []
resources_defaults:
  cpu: 1
  memory: 2GB
  gpu: 0
error_handling: {{}}
# Domain vocabulary: natural-language token → canonical code, e.g.
# vocabulary_mappings:
#   population:
#     european: EUR
vocabulary_mappings: {{}}
# Parameter rules, e.g.
# parameter_constraints:
#   chromosomes:
#     allowed: ["chr1", "chr22"]
#     required: false
parameter_constraints: {{}}
optimization_strategies: []
"""


def new_skill(name: str) -> None:
    """Scaffold a new skill YAML file in the current directory."""
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        console.print(
            "[red]✗ Skill name must be lowercase letters/digits/underscores "
            "starting with a letter[/red]"
        )
        raise typer.Exit(2)
    path = Path(f"{name}_skill.yaml")
    if path.exists():
        console.print(f"[red]❌ {path} already exists[/red]")
        raise typer.Exit(1)
    path.write_text(SKILL_TEMPLATE.format(name=name))
    console.print(f"[green]✓[/green] Created [bold]{path}[/bold]")
    console.print("[dim]Load it with: cpilot skill add " + str(path) + "[/dim]")


skill_app = typer.Typer(help="Manage registered skills")


skill_app.command(name="list")(list_skills)
skill_app.command(name="add")(add_skill)
skill_app.command(name="show")(show_skill)
skill_app.command(name="new")(new_skill)
