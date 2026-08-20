"""computepilot run — execute a workflow (YAML or interactive)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer

from computepilot.cli.ui import console
from computepilot.executors.local import LocalExecutor
from computepilot.models.run import RunStatus
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore
from computepilot.workflow.schema import load_workflow
from computepilot.models.workflow import Workflow
from computepilot.workflow.validator import validate


def run(
    input: str = typer.Argument(
        "", help="Workflow.yaml path, or natural language (with --interactive)", metavar="INPUT"
    ),
    executor: str = typer.Option("local", "--executor", "-e", help="Executor backend"),
    max_concurrency: int = typer.Option(4, "--max-concurrency", "-j", help="Max concurrent tasks"),
    approve: bool = typer.Option(
        False, "--approve", "-y", help="Auto-approve (no confirmation prompt)"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Interactive mode: natural language → plan → execute"
    ),
) -> None:
    """Execute a workflow from YAML or via interactive conversation."""
    if interactive:
        _run_interactive(input or "run a workflow", executor, max_concurrency)
        return

    path = Path(input)
    if not path.exists():
        console.print(f"[red]❌ workflow not found: {path}[/red]")
        raise typer.Exit(2)

    wf = load_workflow(path)
    report = validate(wf)
    if not report.passed:
        console.print("[red]❌ Workflow validation failed:[/red]")
        from computepilot.cli.ui import print_validation_report

        print_validation_report(report, str(path))
        raise typer.Exit(2)

    if not approve:
        console.print(f"[bold]Workflow:[/bold] {wf.name}")
        console.print(f"[bold]Tasks:[/bold] {len(wf.tasks)}")
        confirm = typer.confirm("Proceed with execution?", default=True)
        if not confirm:
            console.print("[yellow]Aborted by user[/yellow]")
            raise typer.Exit(0)

    _execute_workflow(wf, executor, max_concurrency)


def _run_interactive(query: str, executor: str, max_concurrency: int) -> None:
    """Interactive Conductor session → approval → execution."""
    from computepilot.agent.conductor import Conductor
    from computepilot.agent.provider import OpenAIProvider
    from computepilot.skills.base import SkillRegistry

    console.print("[bold]🤖 Interactive mode[/bold] (natural language → workflow → execute)")
    console.print()

    registry = SkillRegistry()
    registry.register_builtins()
    conductor = Conductor(provider=OpenAIProvider(), registry=registry)

    sid = conductor.new_session()
    user_input = query
    rounds = 0

    while rounds < 10:
        resp = conductor.turn_sync(sid, user_input)
        console.print(resp.message)
        console.print()

        if resp.requires_clarification:
            user_input = typer.prompt("  补充信息")
        elif resp.phase == "approval":
            if typer.confirm("  批准执行？", default=True):
                resp = conductor.turn_sync(sid, "yes")
                console.print(resp.message)
                break
            user_input = typer.prompt("  修改意见")
        else:
            break
        rounds += 1

    if rounds >= 10:
        console.print("[red]✗ Multi-turn limit reached[/red]")
        raise typer.Exit(1)

    session = conductor.get_session(sid)
    if session is None or session.current_intent is None:
        console.print("[red]✗ No workflow plan generated[/red]")
        raise typer.Exit(1)

    from computepilot.agent.planner import Planner

    wf = Planner().plan(session.current_intent)
    report = validate(wf)
    if not report.passed:
        from computepilot.cli.ui import print_validation_report

        console.print("[red]✗ Generated workflow validation failed[/red]")
        print_validation_report(report)
        raise typer.Exit(2)

    console.print(f"[green]✓ Workflow '{wf.name}' generated with {len(wf.tasks)} tasks[/green]")
    _execute_workflow(wf, executor, max_concurrency)


def _execute_workflow(wf: Workflow, executor: str, max_concurrency: int) -> None:
    """Run a workflow with the given executor and concurrency."""
    state_dir = Path.home() / ".local" / "share" / "computepilot"
    state_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(state_dir / "state.db")

    run_id = f"run_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_dir = Path.cwd() / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    exe = LocalExecutor()
    engine = Engine(state=store, executor=exe, max_concurrency=max_concurrency)

    try:
        result = asyncio.run(engine.run(workflow=wf, run_id=run_id, run_dir=str(run_dir), env={}))
    except Exception as exc:
        console.print(f"[red]✗ Run failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    if result.status == RunStatus.SUCCEEDED:
        console.print(f"[green]✓ Run '{run_id}' completed successfully[/green]")
    else:
        console.print(f"[red]✗ Run failed: {result.status.value}[/red]")
        raise typer.Exit(1)
