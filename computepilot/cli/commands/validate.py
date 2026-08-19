"""computepilot validate — validate a workflow YAML."""

from __future__ import annotations

from pathlib import Path

import typer

from computepilot.cli.ui import console, print_validation_report
from computepilot.workflow.schema import load_workflow
from computepilot.workflow.validator import validate


def validate_workflow(
    workflow_path: str = typer.Argument(..., help="Path to workflow.yaml", metavar="WORKFLOW"),
) -> None:
    """Validate a workflow YAML file."""
    path = Path(workflow_path)
    if not path.exists():
        console.print(f"[red]❌ workflow not found: {path}[/red]")
        raise typer.Exit(2)

    try:
        wf = load_workflow(path)
    except Exception as exc:
        console.print(f"[red]❌ failed to parse workflow: {exc}[/red]")
        raise typer.Exit(2) from exc

    report = validate(wf)
    print_validation_report(report, workflow_path)

    if not report.passed:
        raise typer.Exit(1)
