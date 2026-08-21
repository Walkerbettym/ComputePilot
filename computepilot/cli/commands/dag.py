"""cpilot dag — visualize a workflow DAG (ascii / mermaid / json / svg)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from computepilot.cli.svgdag import render_svg
from computepilot.cli.ui import console
from computepilot.models.workflow import Task
from computepilot.workflow.dag import DAG, build_dag
from computepilot.workflow.schema import load_workflow

_FORMATS = ("ascii", "mermaid", "json", "svg")


def render_dag(
    workflow_path: str = typer.Argument(..., help="Path to workflow.yaml", metavar="WORKFLOW"),
    format: str = typer.Option(
        "ascii", "--format", "-f", help="Output format: ascii | mermaid | json | svg"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Write result to this file"),
) -> None:
    """Render a workflow's task dependency graph."""
    if format not in _FORMATS:
        console.print(
            f"[red]❌ Unknown format '{format}'. Choose from: {', '.join(_FORMATS)}[/red]"
        )
        raise typer.Exit(2)

    path = Path(workflow_path)
    if not path.exists():
        console.print(f"[red]❌ workflow not found: {path}[/red]")
        raise typer.Exit(2)

    try:
        wf = load_workflow(path)
    except Exception as exc:
        console.print(f"[red]❌ failed to parse workflow: {exc}[/red]")
        raise typer.Exit(2) from exc

    dag = build_dag(wf)
    try:
        order = dag.topological_order()
    except ValueError:
        cycle = dag.find_cycle()
        console.print("[red]❌ Workflow contains a dependency cycle:[/red]")
        console.print(f"  {' -> '.join(cycle)}")
        raise typer.Exit(1) from None

    if format == "mermaid":
        text = _render_mermaid(dag)
    elif format == "json":
        text = json.dumps(_to_json(dag, order), indent=2)
    elif format == "svg":
        cfg_tasks: list[dict[str, object]] = [
            {"id": t.id, "depends_on": list(t.depends_on)} for t in dag.workflow.tasks
        ]
        svg = render_svg(cfg_tasks)
        if svg is None:
            console.print("[red]❌ Cannot render SVG for this workflow[/red]")
            raise typer.Exit(1)
        text = svg
    else:
        text = _render_ascii(dag)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        console.print(f"[green]✓ Written to {out_path}[/green]")
    else:
        console.print(text, markup=False)


def _task_meta(task: Task) -> str:
    meta = f"{task.type.value}, cpu={task.resources.cpu}"
    if task.resources.gpu:
        meta += f", gpu={task.resources.gpu}"
    return meta


def _children_map(dag: DAG) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {t.id: [] for t in dag.workflow.tasks}
    for t in dag.workflow.tasks:
        for dep in t.depends_on:
            children[dep].append(t.id)
    return children


def _render_ascii(dag: DAG) -> str:
    """Render the DAG as an ASCII forest rooted at source tasks."""
    task_map = {t.id: t for t in dag.workflow.tasks}
    children = _children_map(dag)
    roots = [t.id for t in dag.workflow.tasks if not t.depends_on]

    lines: list[str] = []
    visited: set[str] = set()

    def walk(tid: str, prefix: str) -> None:
        visited.add(tid)
        kids = children.get(tid, [])
        for i, kid in enumerate(kids):
            last = i == len(kids) - 1
            marker = "└── " if last else "├── "
            repeat = " ↺" if kid in visited else ""
            lines.append(f"{prefix}{marker}{kid} [{_task_meta(task_map[kid])}]{repeat}")
            if kid not in visited:
                walk(kid, prefix + ("    " if last else "│   "))

    lines.append(f"{dag.workflow.name} ({len(dag.workflow.tasks)} tasks)")
    for root in roots:
        lines.append(f"{root} [{_task_meta(task_map[root])}]")
        walk(root, "")
    return "\n".join(lines)


def _render_mermaid(dag: DAG) -> str:
    """Render the DAG as a mermaid `graph TD` definition."""
    lines = ["graph TD"]
    for t in dag.workflow.tasks:
        lines.append(f'    {t.id}["{t.id}<br/>{_task_meta(t)}"]')
    for t in dag.workflow.tasks:
        for dep in t.depends_on:
            lines.append(f"    {dep} --> {t.id}")
    return "\n".join(lines)


def _to_json(dag: DAG, order: list[str]) -> dict[str, object]:
    """Return a machine-readable node/edge representation."""
    return {
        "workflow": dag.workflow.name,
        "nodes": [
            {
                "id": t.id,
                "type": t.type.value,
                "cpu": t.resources.cpu,
                "gpu": t.resources.gpu,
                "memory": t.resources.memory,
            }
            for t in dag.workflow.tasks
        ],
        "edges": [{"from": dep, "to": t.id} for t in dag.workflow.tasks for dep in t.depends_on],
        "topological_order": order,
    }
