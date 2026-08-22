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


def _deps_of(task: dict[str, object]) -> list[str]:
    raw = task.get("depends_on")
    return [str(d) for d in raw] if isinstance(raw, list) else []


_STATUS_MARK = {
    "succeeded": "✓",
    "failed": "✗",
    "running": "▶",
    "skipped": "»",
}


def _load_run_structure(run_id: str) -> tuple[list[dict[str, object]], dict[str, str]]:
    """Load persisted workflow tasks + task statuses for a run from state.db."""
    from computepilot.runtime.state import StateStore

    db = Path.home() / ".local" / "share" / "computepilot" / "state.db"
    if not db.exists():
        console.print("[red]❌ No state database[/red]")
        raise typer.Exit(2)
    store = StateStore(db)
    data = store.get_run(run_id)
    if data is None:
        store.close()
        console.print(f"[red]❌ Run '{run_id}' not found[/red]")
        raise typer.Exit(2)
    cfg_tasks: list[dict[str, object]] = []
    cfg: dict[str, object] = {}
    try:
        loaded = json.loads(data["config_json"]) if data["config_json"] else None
        if isinstance(loaded, dict):
            cfg = loaded
    except json.JSONDecodeError:
        cfg = {}
    raw_wf = cfg.get("workflow") if isinstance(cfg.get("workflow"), dict) else None
    if isinstance(raw_wf, dict) and isinstance(raw_wf.get("tasks"), list):
        cfg_tasks = [t for t in raw_wf["tasks"] if isinstance(t, dict)]
    statuses: dict[str, str] = {}
    for r in store._conn.execute(
        "SELECT task_id,status FROM task_states WHERE run_id=?", (run_id,)
    ).fetchall():
        statuses[r["task_id"]] = r["status"]
    store.close()
    return cfg_tasks, statuses


def render_dag(
    workflow_path: str = typer.Argument("", help="Path to workflow.yaml", metavar="WORKFLOW"),
    format: str = typer.Option(
        "ascii", "--format", "-f", help="Output format: ascii | mermaid | json | svg"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Write result to this file"),
    run_id: str | None = typer.Option(
        None, "--run", "-r", help="Render the persisted DAG of a run (with live status)"
    ),
) -> None:
    """Render a workflow's task dependency graph."""
    if format not in _FORMATS:
        console.print(
            f"[red]❌ Unknown format '{format}'. Choose from: {', '.join(_FORMATS)}[/red]"
        )
        raise typer.Exit(2)

    run_statuses: dict[str, str] = {}
    if run_id:
        cfg_tasks, run_statuses = _load_run_structure(run_id)
        if not cfg_tasks:
            console.print(
                "[yellow]⚠ Run has no persisted workflow structure (created before v0.5?)[/yellow]"
            )
            raise typer.Exit(2)

        if format == "svg":
            status_map: dict[str, object] = dict(run_statuses)
            text = render_svg(cfg_tasks, status_map) or ""
            if not text:
                console.print("[red]❌ Cannot render SVG for this run[/red]")
                raise typer.Exit(1)
        elif format == "json":
            text = json.dumps(
                {"run": run_id, "nodes": cfg_tasks, "statuses": run_statuses}, indent=2
            )
        elif format == "mermaid":
            lines = ["graph TD"]
            for t in cfg_tasks:
                st = run_statuses.get(str(t["id"]), "")
                mark = _STATUS_MARK.get(st, "")
                cls = f" · {st}" if st else ""
                lines.append(f'    {t["id"]}["{mark} {t["id"]}{cls}<br/>"]')
            for t in cfg_tasks:
                for dep in _deps_of(t):
                    lines.append(f"    {dep} --> {t['id']}")
            text = "\n".join(lines)
        else:
            deps: dict[str, list[str]] = {str(t["id"]): [] for t in cfg_tasks}
            for t in cfg_tasks:
                for d in _deps_of(t):
                    deps.setdefault(str(d), []).append(str(t["id"]))
            roots = [str(t["id"]) for t in cfg_tasks if not _deps_of(t)]
            lines = [f"{run_id} ({len(cfg_tasks)} tasks)"]
            visited: set[str] = set()

            def walk(tid: str, prefix: str) -> None:
                visited.add(tid)
                kids = deps.get(tid, [])
                for i, kid in enumerate(kids):
                    last = i == len(kids) - 1
                    marker = "└── " if last else "├── "
                    repeat = " ↺" if kid in visited else ""
                    st = run_statuses.get(kid, "")
                    mark = _STATUS_MARK.get(st, "·")
                    lines.append(
                        f"{prefix}{marker}{mark} {kid}{(' [' + st + ']') if st else ''}{repeat}"
                    )
                    if kid not in visited:
                        walk(kid, prefix + ("    " if last else "│   "))

            for root in roots:
                st = run_statuses.get(root, "")
                mark = _STATUS_MARK.get(st, "·")
                lines.append(f"{mark} {root}{(' [' + st + ']') if st else ''}")
                walk(root, "")
            text = "\n".join(lines)

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            console.print(f"[green]✓ Written to {out_path}[/green]")
        else:
            console.print(text, markup=False)
        return

    if not workflow_path:
        console.print("[red]❌ Provide WORKFLOW path or --run RUN_ID[/red]")
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
        svg_tasks: list[dict[str, object]] = [
            {"id": t.id, "depends_on": list(t.depends_on)} for t in dag.workflow.tasks
        ]
        svg = render_svg(svg_tasks)
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
