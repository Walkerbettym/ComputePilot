"""ComputePilot Web Dashboard — lightweight FastAPI UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ComputePilot Dashboard")

STATE_DB = Path.home() / ".local" / "share" / "computepilot" / "state.db"

HTML_HEAD = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ComputePilot Dashboard</title>
<style>
body{font-family:-apple-system,sans-serif;max-width:1000px;
margin:0 auto;padding:20px;background:#0d1117;color:#c9d1d9}
h1 { color: #58a6ff; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }
th { color: #8b949e; }
tr:hover { background: #161b22; }
.ok { color: #3fb950; }
.fail { color: #f85149; }
.run { color: #d2a8ff; }
a { color: #58a6ff; text-decoration: none; }
</style>
</head>
<body>
<h1>📊 ComputePilot Dashboard</h1>
"""


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/", response_class=HTMLResponse)
async def index():
    rows = []
    if STATE_DB.exists():
        conn = _get_db()
        rows = conn.execute(
            "SELECT id,workflow_name,status,executor,created_at,finished_at "
            "FROM runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        conn.close()

    html = HTML_HEAD
    html += "<table><tr><th>Run ID</th><th>Workflow</th><th>Status</th><th>Executor</th><th>Created</th></tr>"  # noqa: E501
    for r in rows:
        cls = {"succeeded": "ok", "failed": "fail", "running": "run"}.get(r["status"], "")
        html += (
            f'<tr><td><a href="/run/{r["id"]}">{r["id"][:20]}</a></td>'
            f"<td>{r['workflow_name'] or '-'}</td>"
            f'<td class="{cls}">{r["status"]}</td>'
            f"<td>{r['executor']}</td>"
            f"<td>{str(r['created_at'])[:19]}</td></tr>"
        )
    html += "</table></body></html>"
    if not rows:
        html += '<tr><td colspan="5">No runs yet. Run a workflow first.</td></tr>'

    return HTMLResponse(content=html)


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(run_id: str):
    html = HTML_HEAD
    html += f"<h2>Run: {run_id[:24]}</h2>"
    if not STATE_DB.exists():
        return HTMLResponse(content=html + "<p>No database found.</p></body></html>")

    conn = _get_db()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        return HTMLResponse(content=html + f"<p>Run {run_id} not found.</p></body></html>")

    html += "<table>"
    for key in (
        "id",
        "workflow_name",
        "status",
        "executor",
        "created_at",
        "started_at",
        "finished_at",
    ):  # noqa: E501
        html += f"<tr><th>{key}</th><td>{row[key] or '-'}</td></tr>"
    html += "</table>"

    tasks = conn.execute(
        "SELECT task_id,status,exit_code,error FROM task_states WHERE run_id=?",
        (run_id,),
    ).fetchall()
    conn.close()

    if tasks:
        html += (
            "<h3>Tasks</h3><table><tr><th>Task</th><th>Status</th><th>Exit</th><th>Error</th></tr>"  # noqa: E501
        )
        for t in tasks:
            html += f"<tr><td>{t['task_id']}</td>"
            html += f"<td>{t['status']}</td>"
            html += f"<td>{t['exit_code'] or '-'}</td>"
            html += f"<td>{t['error'] or '-'}</td></tr>"
        html += "</table>"

    html += '<br><a href="/">← Back</a></body></html>'
    return HTMLResponse(content=html)


def main():
    import uvicorn

    print("🌐 ComputePilot Dashboard: http://localhost:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")


if __name__ == "__main__":
    main()
