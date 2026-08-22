"""ComputePilot Python API — drive the engine directly from Python/Jupyter.

Sync-first wrappers over the runtime components. All functions accept an
optional ``state_dir`` so embeddings (tests, notebooks, services) can use an
isolated state database instead of the user-wide default.

Example::

    from computepilot import api

    run = api.run("workflow.yaml", params={"epochs": 50})
    print(run.id, run.status)
    for art in api.artifacts(run.id):
        print(art["path"], art["checksum"])
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from computepilot.artifacts.provenance import ProvenanceBuilder
from computepilot.artifacts.store import ArtifactStore
from computepilot.executors.local import LocalExecutor
from computepilot.models.run import Run, RunStatus
from computepilot.runtime.engine import Engine
from computepilot.runtime.state import StateStore
from computepilot.workflow.schema import load_workflow
from computepilot.workflow.validator import validate

DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "computepilot"

__all__ = [
    "run",
    "resume",
    "status",
    "list_runs",
    "artifacts",
    "report",
    "cancel",
]


def _store(state_dir: str | Path | None = None) -> StateStore:
    d = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return StateStore(d / "state.db")


def run(
    workflow_path: str | Path,
    *,
    params: dict[str, str] | None = None,
    executor: str = "local",
    max_concurrency: int = 4,
    state_dir: str | Path | None = None,
    run_dir: str | Path | None = None,
) -> Run:
    """Validate and execute a workflow; block until it reaches a terminal state.

    Raises :class:`MissingParameterError` for unbound ``${key}`` placeholders
    and :class:`ValueError` when validation fails.
    """
    wf = load_workflow(workflow_path, params)
    report_ = validate(wf)
    if not report_.passed:
        errors = [f"{e.code}: {e.message}" for e in report_.errors if e.level == "error"]
        raise ValueError("workflow validation failed:\n" + "\n".join(errors))

    store = _store(state_dir)
    run_id = f"run_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    resolved_dir = Path(run_dir) if run_dir else Path.cwd() / "runs" / run_id
    resolved_dir.mkdir(parents=True, exist_ok=True)

    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=max_concurrency)
    result = asyncio.run(
        engine.run(
            workflow=wf,
            run_id=run_id,
            run_dir=str(resolved_dir),
            env={},
            config={
                "total_tasks": len(wf.tasks),
                "workflow": {
                    "tasks": [
                        {"id": t.id, "type": t.type.value, "depends_on": t.depends_on}
                        for t in wf.tasks
                    ]
                },
            },
        )
    )
    store.close()
    return result


def resume(
    run_id: str,
    workflow_path: str | Path,
    *,
    max_concurrency: int = 4,
    state_dir: str | Path | None = None,
    retry_failed: bool = False,
) -> Run:
    """Resume a previously-started run, skipping completed tasks.

    With ``retry_failed=True`` tasks that FAILED earlier are re-queued
    before resuming.
    """
    wf = load_workflow(workflow_path)
    store = _store(state_dir)
    if retry_failed:
        store.reset_failed_tasks(run_id)
    engine = Engine(state=store, executor=LocalExecutor(), max_concurrency=max_concurrency)
    result = asyncio.run(
        engine.resume(workflow=wf, run_id=run_id, run_dir=Path(workflow_path).parent, env={})
    )
    store.close()
    return result


def status(run_id: str, *, state_dir: str | Path | None = None) -> dict[str, Any]:
    """Return run metadata plus per-task states, or raise KeyError if unknown."""
    store = _store(state_dir)
    data = store.get_run(run_id)
    if data is None:
        store.close()
        raise KeyError(f"run '{run_id}' not found")
    tasks = []
    for tid in {
        r["task_id"]
        for r in store._conn.execute(
            "SELECT task_id FROM task_states WHERE run_id=?", (run_id,)
        ).fetchall()
    }:
        details = store.get_task_details(run_id, tid)
        if details:
            tasks.append(details)
    store.close()
    return {"run": data, "tasks": sorted(tasks, key=lambda t: t["task_id"])}


def list_runs(limit: int = 20, *, state_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the most recent runs (id/status/executor/created_at)."""
    store = _store(state_dir)
    rows = store._conn.execute(
        "SELECT id,status,executor,created_at FROM runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    store.close()
    return [dict(r) for r in rows]


def artifacts(run_id: str, *, state_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Return registered artifact metadata for a run."""
    store = _store(state_dir)
    arts = ArtifactStore(store).list_for_run(run_id)
    store.close()
    return arts


def report(
    run_id: str,
    *,
    out_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
) -> Path:
    """Generate manifest.json + report.md for a run; returns the output dir."""
    store = _store(state_dir)
    data = store.get_run(run_id)
    if data is None:
        store.close()
        raise KeyError(f"run '{run_id}' not found")

    run = Run(
        id=data["id"],
        workflow_id=data["workflow_id"],
        workflow_name=data.get("workflow_name", ""),
        workflow_sha256=data["workflow_sha256"],
        status=RunStatus(data["status"]),
        executor=data["executor"],
        config=__import__("json").loads(data["config_json"]),
        created_at=datetime.fromisoformat(data["created_at"]),
    )
    arts = ArtifactStore(store).list_for_run(run_id)
    store.close()

    builder = ProvenanceBuilder(run)
    dest = Path(out_dir) if out_dir else (Path(run.run_dir) if run.run_dir else Path.cwd())
    dest.mkdir(parents=True, exist_ok=True)
    builder.write_manifest(dest / "manifest.json", arts)

    lines = [
        f"# Workflow Report: {run.workflow_name}",
        "",
        f"- **Run ID:** {run.id}",
        f"- **Status:** {run.status.value}",
        f"- **Workflow SHA256:** {run.workflow_sha256}",
        "",
        "## Artifacts",
        "",
    ]
    if arts:
        lines.append(f"{len(arts)} artifact(s):")
        lines.append("")
        lines.append("| ID | Type | Size (B) | SHA256 | Path |")
        lines.append("|---|---|---|---|---|")
        for a in arts:
            lines.append(
                f"| {str(a['id'])[:12]} | {a['type']} | {a['size']} "
                f"| `{str(a['checksum'])[:16]}…` | `{a['path']}` |"
            )
    else:
        lines.append("*No artifacts registered.*")
    (dest / "report.md").write_text("\n".join(lines) + "\n")
    return dest


def cancel(run_id: str, *, state_dir: str | Path | None = None) -> None:
    """Mark a non-terminal run as CANCELLED."""
    store = _store(state_dir)
    if store.get_run(run_id) is None:
        store.close()
        raise KeyError(f"run '{run_id}' not found")
    store.update_run_status(run_id, RunStatus.CANCELLED)
    store.close()


def verify(run_a: str, run_b: str, *, state_dir: str | Path | None = None) -> dict[str, Any]:
    """Compare two runs for reproducibility; returns the check matrix.

    Mirrors ``cpilot verify``: workflow hash, task outcomes, artifact checksums.
    """
    import sqlite3

    from computepilot.cli.commands.verify import _load_run

    db = (Path(state_dir) if state_dir else DEFAULT_STATE_DIR) / "state.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    a = _load_run(conn, run_a)
    b = _load_run(conn, run_b)
    conn.close()
    if a is None:
        raise KeyError(f"run '{run_a}' not found")
    if b is None:
        raise KeyError(f"run '{run_b}' not found")

    ta = {t["task_id"]: (t["status"], t["exit_code"]) for t in a["tasks"]}
    tb = {t["task_id"]: (t["status"], t["exit_code"]) for t in b["tasks"]}

    def _idx(arts: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
        out: dict[tuple[str, str], list[str]] = {}
        for x in arts:
            out.setdefault((str(x["task_id"]), str(x["type"])), []).append(str(x["checksum"]))
        return {k: sorted(v) for k, v in out.items()}

    aa = _idx(a["artifacts"])
    ab = _idx(b["artifacts"])

    checks: list[dict[str, Any]] = [
        {
            "category": "workflow",
            "detail": "sha256",
            "match": a["workflow_sha256"] == b["workflow_sha256"],
        },
        *(
            {"category": "task", "detail": tid, "match": ta.get(tid) == tb.get(tid)}
            for tid in sorted(set(ta) | set(tb))
        ),
        *(
            {"category": "artifact", "detail": f"{k[0]}:{k[1]}", "match": aa.get(k) == ab.get(k)}
            for k in sorted(set(aa) | set(ab), key=str)
        ),
    ]
    return {"reproducible": all(c["match"] for c in checks), "checks": checks}
