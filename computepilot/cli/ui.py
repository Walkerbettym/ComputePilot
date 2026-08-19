"""Rich console helpers for computepilot CLI output."""

from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from computepilot.models.run import Run, RunStatus
from computepilot.workflow.validator import ValidationReport

console = Console()


def print_validation_report(
    report: ValidationReport,
    workflow_path: str | Path | None = None,
) -> None:
    """Render a validation report to the console."""
    path_str = f" {workflow_path}" if workflow_path else ""
    if report.passed:
        console.print(f"[green]✓[/green]{path_str} — validation passed")
        return

    for err in report.errors:
        level_style = "red" if err.level == "error" else "yellow"
        prefix = "❌" if err.level == "error" else "⚠"
        loc = f" [{err.location}]" if err.location else ""
        console.print(f"[{level_style}]{prefix} {err.code}: {err.message}{loc}[/{level_style}]")

    error_count = sum(1 for e in report.errors if e.level == "error")
    warning_count = sum(1 for e in report.errors if e.level == "warning")
    parts = []
    if error_count:
        parts.append(f"[red]{error_count} error(s)[/red]")
    if warning_count:
        parts.append(f"[yellow]{warning_count} warning(s)[/yellow]")
    console.print(f"[bold]{' | '.join(parts)}[/bold]")


def print_run_status(run: Run) -> None:
    """Render a single run summary."""
    status_colors = {
        RunStatus.CREATED: "blue",
        RunStatus.VALIDATING: "yellow",
        RunStatus.PENDING_APPROVAL: "yellow",
        RunStatus.RUNNING: "cyan",
        RunStatus.SUCCEEDED: "green",
        RunStatus.FAILED: "red",
        RunStatus.CANCELLED: "dim",
    }
    color = status_colors.get(run.status, "white")
    console.print(f"  Run [bold]{run.id}[/bold] — [{color}]{run.status.value}[/{color}]")


def print_run_detail(run: Run, tasks: list[dict[str, Any]] | None = None) -> None:
    """Render a detailed run view."""
    table = Table(title=f"Run {run.id}")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Status", run.status.value)
    table.add_row("Workflow ID", str(run.workflow_id))
    table.add_row("Executor", run.executor)
    table.add_row("Created", run.created_at.isoformat() if run.created_at else "-")
    table.add_row("Started", run.started_at.isoformat() if run.started_at else "-")
    table.add_row("Finished", run.finished_at.isoformat() if run.finished_at else "-")
    table.add_row("Run Dir", str(run.run_dir) if run.run_dir else "-")

    console.print(table)

    if tasks:
        task_table = Table(title="Task States")
        task_table.add_column("Task ID", style="bold")
        task_table.add_column("Status")
        task_table.add_column("Exit Code")
        task_table.add_column("Error")

        for t in tasks:
            status = t.get("status", "-")
            exit_code = str(t.get("exit_code", "")) if t.get("exit_code") is not None else "-"
            error = t.get("error", "") or "-"
            task_table.add_row(t.get("task_id", "-"), status, exit_code, error)

        console.print(task_table)


def print_task_logs(
    events: list[dict[str, Any]],
    task_id: str | None = None,
    tail: int = 50,
) -> None:
    """Render task event logs."""
    filtered = events
    if task_id:
        filtered = [e for e in events if e.get("task_id") == task_id]

    if not filtered:
        console.print("[dim]No log entries found.[/dim]")
        return

    table = Table(title=f"Logs{' for ' + task_id if task_id else ''}")
    table.add_column("Time", style="dim")
    table.add_column("Task ID", style="bold")
    table.add_column("Event")

    for entry in filtered[-tail:]:
        at = entry.get("at", "")[:19]
        tid = entry.get("task_id", "-")
        event = entry.get("event", "-")
        table.add_row(at, tid, event)

    console.print(table)


def build_task_summary(task_states: list[dict[str, Any]]) -> dict[str, int]:
    """Build a summary dict of task status counts."""
    counter: Counter[str] = Counter()
    for ts in task_states:
        counter[ts.get("status", "unknown")] += 1
    return dict(counter)
