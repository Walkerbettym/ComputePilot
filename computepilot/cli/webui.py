# ruff: noqa: E501
"""ComputePilot Web Dashboard — lightweight FastAPI UI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from computepilot.cli.svgdag import render_svg

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
.t{color:#8b949e;font-size:.85em}
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

    # -- Events (latest 20) ----------------------------------------------------
    event_rows = conn.execute(
        "SELECT task_id,event,at FROM task_events WHERE run_id=? ORDER BY id DESC LIMIT 20",
        (run_id,),
    ).fetchall()
    if event_rows:
        body += "<h3>Events</h3><table><tr><th>Time</th><th>Task</th><th>Event</th></tr>"
        for ev in reversed(event_rows):
            at = str(ev["at"])[:19]
            body += (
                f'<tr><td class="t">{at}</td>'
                f"<td><code>{ev['task_id']}</code></td><td>{ev['event']}</td></tr>"
            )
        body += "</table>"

    tasks = conn.execute(
        "SELECT task_id,status,exit_code,error FROM task_states WHERE run_id=?", (run_id,)
    ).fetchall()
    conn.close()
    if cfg_tasks:
        status_by_task = {t["task_id"]: t["status"] for t in tasks}
        svg = render_svg(cfg_tasks, status_by_task)
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
    body += (
        f'<div class="nav"><a href="/run/{run_id}/live">⚡ Live events</a> · '
        '<a href="/">← Back</a></div>'
    )
    return HTMLResponse(content=body)


@app.get("/run/{run_id}/live", response_class=HTMLResponse)
async def run_live(run_id: str) -> HTMLResponse:
    """Auto-polling live event stream for a run (uses the cursor API)."""
    body = _pg(f"Live {run_id[:20]}", "", auto_refresh=False)
    body += f"<h2>Live events — <code>{run_id[:28]}</code></h2>"
    body += (
        '<div id="events" style="font-family:monospace;font-size:.85em;'
        "background:#161b22;border:1px solid #30363d;border-radius:8px;"
        'padding:16px;min-height:200px"></div>'
        '<div class="nav"><a href="/run/' + run_id + '">← Run detail</a></div>'
        "<script>"
        "const box=document.getElementById('events');let cursor=0;"
        "async function poll(){try{"
        f"const r=await fetch('/api/run/{run_id}/events?after='+cursor);"
        "const d=await r.json();cursor=d.cursor||cursor;"
        "for(const e of d.events){const div=document.createElement('div');"
        "div.textContent=`${(e.at||'').slice(0,19)}  ${e.task_id}  ${e.event}`;"
        "box.appendChild(div);}"
        "}catch(err){}setTimeout(poll,1500);}"
        "poll();</script>"
    )
    return HTMLResponse(content=body)


# -- JSON API (scripting / external tooling) -----------------------------------


def _cfg_workflow(row: sqlite3.Row) -> dict[str, object]:
    """Extract the persisted workflow structure from a runs row, if any."""
    try:
        cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    wf = cfg.get("workflow") if isinstance(cfg, dict) else None
    return wf if isinstance(wf, dict) else {}


@app.get("/api/runs")
async def api_runs() -> JSONResponse:
    """List all runs as JSON."""
    if not STATE_DB.exists():
        return JSONResponse(content={"runs": []})
    conn = _db()
    rows = conn.execute(
        "SELECT id,status,executor,workflow_name,created_at FROM runs ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return JSONResponse(content={"runs": [dict(r) for r in rows]})


@app.get("/api/run/{run_id}")
async def api_run(run_id: str) -> JSONResponse:
    """Full run detail: metadata, task states, events, and workflow structure."""
    if not STATE_DB.exists():
        return JSONResponse(content={"error": "no database"}, status_code=404)
    conn = _db()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        return JSONResponse(content={"error": "run not found"}, status_code=404)
    tasks = [
        dict(t)
        for t in conn.execute(
            "SELECT task_id,status,attempt,exit_code,error FROM task_states WHERE run_id=?",
            (run_id,),
        ).fetchall()
    ]
    events = [
        dict(ev)
        for ev in conn.execute(
            "SELECT id,task_id,event,at,payload FROM task_events WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    ]
    conn.close()
    return JSONResponse(
        content={
            "run": {
                "id": row["id"],
                "status": row["status"],
                "workflow_name": row["workflow_name"],
                "workflow_sha256": row["workflow_sha256"],
                "executor": row["executor"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "config": _cfg_workflow(row),
            },
            "tasks": tasks,
            "events": events,
        }
    )


@app.get("/api/run/{run_id}/events")
async def api_events(run_id: str, after: int = 0) -> JSONResponse:
    """Incremental event feed: events with id > ``after`` (poll-friendly tail)."""
    if not STATE_DB.exists():
        return JSONResponse(content={"events": [], "cursor": after})
    conn = _db()
    exists = conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
    if exists is None:
        conn.close()
        return JSONResponse(content={"error": "run not found"}, status_code=404)
    rows = conn.execute(
        "SELECT id,task_id,event,at,payload FROM task_events "
        "WHERE run_id=? AND id > ? ORDER BY id LIMIT 500",
        (run_id, after),
    ).fetchall()
    conn.close()
    cursor = max((r["id"] for r in rows), default=after)
    return JSONResponse(content={"events": [dict(r) for r in rows], "cursor": cursor})


def main() -> None:
    import uvicorn

    print("🌐 ComputePilot Dashboard → http://0.0.0.0:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
