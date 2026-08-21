# ruff: noqa: E501
"""ComputePilot Web Dashboard — lightweight FastAPI UI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ComputePilot Dashboard")

STATE_DB = Path.home() / ".local" / "share" / "computepilot" / "state.db"

CSS = """<style>
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:24px;background:#0d1117;color:#c9d1d9}
h1{color:#58a6ff;font-size:1.6em;margin-bottom:4px}
h2{color:#58a6ff;font-size:1.2em}
.sub{color:#8b949e;margin-top:0;font-size:0.9em}
.stats{display:flex;gap:16px;margin:20px 0;flex-wrap:wrap}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 24px;min-width:140px;flex:1}
.card .n{font-size:2em;font-weight:600}
.card .l{font-size:0.8em;color:#8b949e;margin-top:4px}
table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #30363d;white-space:nowrap}
th{color:#8b949e;font-weight:500;font-size:0.85em;text-transform:uppercase;letter-spacing:.5px}
tr:hover{background:#161b22}
.s-ok{color:#3fb950}
.s-fail{color:#f85149}
.bar{width:100%;height:6px;background:#21262d;border-radius:3px;overflow:hidden}
.bar-f{height:100%;border-radius:3px;transition:width .5s}
.bg-ok{background:#3fb950}
.bg-fail{background:#f85149}
.bdg{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.8em;font-weight:500}
.bg-ok2{background:rgba(63,185,80,.15);color:#3fb950}
.bg-fail2{background:rgba(248,81,73,.15);color:#f85149}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
.nav{margin:16px 0}
.empty{color:#8b949e;text-align:center;padding:40px}
code{padding:2px 6px;background:#21262d;border-radius:4px;font-size:.85em}
</style>"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _pg(title: str, body: str, auto_refresh: bool = False) -> str:
    r = '<meta http-equiv="refresh" content="5">' if auto_refresh else ""
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">{r}<title>{title}</title>{CSS}</head><body>
<h1>⚡ ComputePilot</h1><div class="sub">Workflow Runtime Dashboard</div>{body}</body></html>"""


def _card(n: int | str, label: str, color: str = "") -> str:
    sc = f' style="color:{color}"' if color else ""
    return f'<div class="card"><div class="n"{sc}>{n}</div><div class="l">{label}</div></div>'


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    if not STATE_DB.exists():
        return HTMLResponse(content=_pg("Dashboard", '<p class="empty">No runs yet.</p>'))

    conn = _db()
    total = conn.execute("SELECT COUNT(*) as c FROM runs").fetchone()["c"]
    ok = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status='succeeded'").fetchone()["c"]
    fail = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status='failed'").fetchone()["c"]
    runn = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status='running'").fetchone()["c"]
    ok_pct = round(ok / total * 100, 1) if total else 0
    fpct = round(fail / total * 100, 1) if total else 0

    body = f'<div class="stats">{_card(total, "Total Runs", "#58a6ff")}{_card(ok, "Succeeded", "#3fb950")}{_card(fail, "Failed", "#f85149")}{_card(runn, "Running", "#d2a8ff")}{_card(ok_pct, "Success Rate", "#e3b341")}</div>'
    body += f'<div style="display:flex;gap:2px;height:8px;border-radius:4px;overflow:hidden;margin:0 0 20px"><div style="width:{ok_pct}%;background:#3fb950"></div><div style="width:{fpct}%;background:#f85149"></div></div>'

    rows = conn.execute(
        "SELECT id,workflow_name,status,executor,created_at FROM runs ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    has_run = any(r["status"] == "running" for r in rows)
    page = _pg("Dashboard", body, auto_refresh=has_run)
    page += "<table><tr><th>Run ID</th><th>Workflow</th><th>Status</th><th>Executor</th><th>Age</th></tr>"
    for r in rows:
        age = ""
        if r["created_at"]:
            try:
                cd = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                d = datetime.now(tz=UTC) - cd
                age = (
                    f"{int(d.total_seconds() // 60)}m"
                    if d.total_seconds() < 3600
                    else f"{d.total_seconds() / 3600:.1f}h"
                )
            except (ValueError, TypeError):
                age = str(r["created_at"])[:10]
        c2 = {"succeeded": "bg-ok2", "failed": "bg-fail2", "running": "bdg"}.get(
            r["status"], "bg-ok2"
        )
        page += f'<tr><td><a href="/run/{r["id"]}">{r["id"][:16]}</a></td>'
        page += f"<td>{r['workflow_name'] or '-'}</td>"
        page += f'<td><span class="bdg {c2}">{r["status"]}</span></td>'
        page += f"<td>{r['executor']}</td><td>{age}</td></tr>"
    page += "</table></body></html>"
    return HTMLResponse(content=page)


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(run_id: str) -> HTMLResponse:
    if not STATE_DB.exists():
        return HTMLResponse(content=_pg("Error", '<p class="empty">No database.</p>'))
    conn = _db()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        return HTMLResponse(
            content=_pg("Not Found", f'<p class="empty">Run {run_id} not found.</p>')
        )

    is_running = row["status"] == "running"
    body = _pg(f"Run {run_id[:20]}", "", auto_refresh=is_running)
    body += f"<h2>Run <code>{run_id[:28]}</code></h2><table>"
    for k in ("status", "workflow_name", "executor", "created_at", "started_at", "finished_at"):
        body += f"<tr><th>{k}</th><td>{row[k] or '-'}</td></tr>"
    cfg_tasks: list[dict[str, object]] = []
    if row["config_json"] and row["config_json"] != "{}":
        from contextlib import suppress

        with suppress(json.JSONDecodeError, TypeError):
            cfg = json.loads(row["config_json"])
            wf_cfg = cfg.get("workflow") if isinstance(cfg, dict) else None
            if isinstance(wf_cfg, dict):
                raw_tasks = wf_cfg.get("tasks")
                if isinstance(raw_tasks, list):
                    cfg_tasks = [t for t in raw_tasks if isinstance(t, dict)]
    body += "</table>"

    tasks = conn.execute(
        "SELECT task_id,status,exit_code,error FROM task_states WHERE run_id=?", (run_id,)
    ).fetchall()
    conn.close()
    if cfg_tasks:
        status_by_task = {t["task_id"]: t["status"] for t in tasks}
        svg = _dag_svg(cfg_tasks, status_by_task)
        if svg:
            body += f"<h3>DAG</h3>{svg}"
    if tasks:
        done = sum(1 for t in tasks if t["status"] in ("succeeded", "failed", "skipped"))
        pct = round(done / len(tasks) * 100, 1) if tasks else 0
        bc = "bg-fail" if any(t["status"] == "failed" for t in tasks) else "bg-ok"
        body += "<h3>Tasks</h3>"
        body += (
            '<div style="display:flex;align-items:center;gap:10px;color:#8b949e;font-size:.85em">'
        )
        body += f'<div style="flex:1"><div class="bar"><div class="bar-f {bc}" style="width:{pct}%"></div></div></div>'
        body += f"<span>{done}/{len(tasks)}</span></div>"
        body += "<table><tr><th>Task</th><th>Status</th><th>Exit</th><th>Error</th></tr>"
        for t in tasks:
            sc = {"succeeded": "s-ok", "failed": "s-fail"}.get(t["status"], "")
            body += f'<tr><td>{t["task_id"]}</td><td class="{sc}">{t["status"]}</td><td>{t["exit_code"] or "-"}</td><td style="white-space:normal;max-width:300px;word-break:break-all">{t["error"] or "-"}</td></tr>'
        body += "</table>"
    body += '<div class="nav"><a href="/">← Back</a></div>'
    return HTMLResponse(content=body)


_NODE_W, _NODE_H, _GAP_X, _GAP_Y = 130, 34, 46, 16

_STATUS_FILL = {
    "succeeded": "#12351f",
    "failed": "#3d1418",
    "running": "#1c2f4a",
    "skipped": "#2a2f36",
}


def dag_svg(cfg_tasks: list[dict[str, object]]) -> str | None:
    """Render a layered left-to-right SVG dependency graph (no external deps)."""
    return _dag_svg(cfg_tasks, {})


def _dag_svg(cfg_tasks: list[dict[str, object]], status_by_task: dict[str, object]) -> str | None:
    """Layered SVG from [{id, depends_on}] task dicts; None when empty/oversized."""
    ids = [str(t["id"]) for t in cfg_tasks if t.get("id")]
    if not ids or len(ids) > 200:
        return None
    idset = set(ids)
    deps: dict[str, list[str]] = {}
    for t in cfg_tasks:
        tid = t.get("id")
        if not tid:
            continue
        raw = t.get("depends_on")
        plist = [str(d) for d in raw if d in idset] if isinstance(raw, list) else []
        deps[str(tid)] = plist

    # Kahn layering: layer[n] = 1 + max(layer[p] for p in deps)
    indeg = {i: len(deps[i]) for i in ids}
    layer = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    seen = 0
    while queue:
        nxt: list[str] = []
        for nid in queue:
            seen += 1
            for cid, plist in deps.items():
                if nid in plist and cid in indeg:
                    indeg[cid] -= 1
                    layer[cid] = max(layer[cid], layer[nid] + 1)
                    if indeg[cid] == 0:
                        nxt.append(cid)
        queue = nxt
    if seen != len(ids):  # cycle — skip rendering
        return None

    columns: dict[int, list[str]] = {}
    for i in ids:
        columns.setdefault(layer[i], []).append(i)

    def node_xy(nid: str) -> tuple[float, float]:
        col = columns[layer[nid]]
        row = col.index(nid)
        x = layer[nid] * (_NODE_W + _GAP_X)
        y = row * (_NODE_H + _GAP_Y)
        return x + 10, y + 10

    width = (max(columns) + 1) * (_NODE_W + _GAP_X)
    height = max(len(c) for c in columns.values()) * (_NODE_H + _GAP_Y) + 20
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'style="max-width:{width}px;background:#0d1117;border:1px solid #30363d;'
        f'border-radius:8px;margin:12px 0">',
        '<defs><marker id="arw" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#58a6ff"/></marker></defs>',
    ]
    from html import escape as e

    for t in cfg_tasks:
        for d in deps[str(t["id"])]:
            x1, y1 = node_xy(d)
            x2, y2 = node_xy(str(t["id"]))
            parts.append(
                f'<path d="M{x1 + _NODE_W},{y1 + _NODE_H // 2} '
                f"C{x1 + _NODE_W + _GAP_X // 2},{y1 + _NODE_H // 2} "
                f'{x2 - _GAP_X // 2},{y2 + _NODE_H // 2} {x2},{y2 + _NODE_H // 2}" '
                'stroke="#58a6ff" stroke-width="1.2" fill="none" marker-end="url(#arw)" '
                'opacity="0.55"/>'
            )
    for tid in ids:
        x, y = node_xy(tid)
        st = status_by_task.get(tid)
        fill = _STATUS_FILL.get(str(st), "#161b22")
        stroke = (
            "#3fb950"
            if st == "succeeded"
            else "#f85149"
            if st == "failed"
            else "#d2a8ff"
            if st == "running"
            else "#30363d"
        )
        parts.append(
            f'<rect x="{x}" y="{y}" width="{_NODE_W}" height="{_NODE_H}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        )
        label = e(tid[:18])
        parts.append(
            f'<text x="{x + _NODE_W / 2}" y="{y + _NODE_H / 2 + 4}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="11.5" fill="#c9d1d9">{label}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    import uvicorn

    print("🌐 ComputePilot Dashboard → http://0.0.0.0:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
