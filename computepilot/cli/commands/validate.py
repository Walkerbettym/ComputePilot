"""cpilot validate — validate a workflow YAML."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from computepilot.cli.ui import console, print_validation_report
from computepilot.workflow.params import MissingParameterError, parse_set_args
from computepilot.workflow.schema import load_workflow
from computepilot.workflow.validator import validate


def validate_workflow(
    workflow_path: str = typer.Argument(..., help="Path to workflow.yaml", metavar="WORKFLOW"),
    set_param: list[str] | None = typer.Option(
        None, "--set", help="Set workflow parameter before validating, e.g. --set epochs=50"
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable report"),
) -> None:
    """Validate a workflow YAML file."""
    path = Path(workflow_path)
    if not path.exists():
        console.print(f"[red]❌ workflow not found: {path}[/red]")
        raise typer.Exit(2)

    try:
        params = parse_set_args(set_param)
        wf = load_workflow(path, params)
    except MissingParameterError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(2) from exc
    except ValueError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(2) from exc
    except Exception as exc:
        console.print(f"[red]❌ failed to parse workflow: {exc}[/red]")
        raise typer.Exit(2) from exc

    report = validate(wf)

    if json_output:
        payload = {
            "workflow": str(path),
            "passed": report.passed,
            "issues": [
                {
                    "code": e.code,
                    "level": e.level,
                    "message": e.message,
                    **({"location": e.location} if e.location else {}),
                }
                for e in report.errors
            ],
        }
        console.print(json.dumps(payload, indent=2), markup=False)
    else:
        print_validation_report(report, workflow_path)

    if not report.passed:
        raise typer.Exit(1)
