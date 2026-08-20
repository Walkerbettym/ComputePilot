"""cpilot plan — generate a workflow from a natural language description."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from computepilot.agent.cost import CostEstimator
from computepilot.agent.generator import WorkflowGenerator
from computepilot.workflow.schema import dump_workflow

console = Console()


def plan(
    description: str = typer.Argument(
        ..., help="Natural language description of the workflow to generate"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Save workflow YAML to this file"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="LLM model to use (overrides COMPUTEPILOT_LLM_MODEL)"
    ),
    show_cost: bool = typer.Option(True, "--cost/--no-cost", help="Show estimated cost"),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Multi-turn conversation with clarification (requires Conductor)",
    ),
) -> None:
    if interactive:
        from computepilot.agent.conductor import Conductor
        from computepilot.agent.provider import OpenAIProvider
        from computepilot.skills.base import SkillRegistry

        registry = SkillRegistry()
        registry.register_builtins()
        cond = Conductor(provider=OpenAIProvider(model=model), registry=registry)
        sid = cond.new_session()
        user_input = description
        rounds = 0
        while rounds < 10:
            resp = cond.turn_sync(sid, user_input)
            console.print(resp.message)
            if resp.requires_clarification:
                user_input = typer.prompt("补充")
            elif resp.phase == "approval":
                if typer.confirm("批准执行?", default=True):
                    resp = cond.turn_sync(sid, "yes")
                    console.print(resp.message)
                    break
                user_input = typer.prompt("修改意见")
            else:
                break
            rounds += 1
        return
    """Generate a workflow from a natural language description."""
    provider_type = os.environ.get("COMPUTEPILOT_LLM_PROVIDER", "openai").lower()

    if provider_type != "openai":
        console.print(f"[red]Unsupported provider: {provider_type}[/red]")
        raise typer.Exit(1)

    provider = OpenAIProvider(model=model)
    generator = WorkflowGenerator(provider)

    with console.status("[cyan]Extracting intent and generating workflow...[/cyan]"):
        try:
            workflow = generator.generate(description, model=model)
        except Exception as exc:
            console.print(f"[red]✗ Generation failed: {exc}[/red]")
            raise typer.Exit(1) from exc

    # Output the workflow YAML
    yaml_str = dump_workflow(workflow)
    console.print("[green]✓[/green] Generated workflow:")
    console.print(yaml_str)

    # Cost estimate
    if show_cost:
        estimator = CostEstimator()
        estimate = estimator.estimate(workflow)
        cost_str = f"${estimate.total_cost:.2f} {estimate.currency}"
        console.print(f"[bold]Estimated cost:[/bold] {cost_str}")
        console.print(f"[dim]Tasks: {estimate.task_count}[/dim]")

    # Save to file if requested
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_str)
        console.print(f"[green]✓[/green] Saved workflow to {out_path}")
