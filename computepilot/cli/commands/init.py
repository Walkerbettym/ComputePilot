"""cpilot init — scaffold a new workflow."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from computepilot.cli.templates import TEMPLATES

console = Console()

DEFAULT_WORKFLOW = """\
name: my_workflow
description: "My ComputePilot workflow"
tasks:
  - id: hello
    command: echo "Hello, ComputePilot!"
    type: shell
"""


def init(
    path: str = typer.Argument(".", help="Directory to scaffold the workflow in"),
    name: str | None = typer.Option(None, "--name", "-n", help="Workflow name"),
    template: str | None = typer.Option(
        None,
        "--template",
        "-t",
        help=f"Built-in template ({', '.join(TEMPLATES)})",
    ),
) -> None:
    """Scaffold a new workflow.yaml in the given directory."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    wf_path = target / "workflow.yaml"

    if wf_path.exists():
        console.print(f"[red]❌ {wf_path} already exists[/red]")
        raise typer.Exit(1)

    if template:
        if template not in TEMPLATES:
            console.print(f"[red]❌ Unknown template '{template}'.[/red]")
            console.print(f"[dim]Available: {', '.join(sorted(TEMPLATES))}[/dim]")
            raise typer.Exit(2)
        content = TEMPLATES[template]
        if name:
            first_line = content.split("\n", 1)[0]
            content = content.replace(first_line, f"name: {name}", 1)
    else:
        content = DEFAULT_WORKFLOW
        if name:
            content = content.replace("my_workflow", name, 1)

    wf_path.write_text(content)
    console.print(
        f"[green]✓[/green] Created {wf_path}" + (f" from template '{template}'" if template else "")
    )
