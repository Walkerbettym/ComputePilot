"""Layered SVG dependency-graph renderer shared by CLI (`cpilot dag`) and webui."""

from __future__ import annotations

from html import escape

_NODE_W, _NODE_H, _GAP_X, _GAP_Y = 130, 34, 46, 16

_STATUS_FILL = {
    "succeeded": "#12351f",
    "failed": "#3d1418",
    "running": "#1c2f4a",
    "skipped": "#2a2f36",
}

_STATUS_STROKE = {
    "succeeded": "#3fb950",
    "failed": "#f85149",
    "running": "#d2a8ff",
}


def render_svg(
    cfg_tasks: list[dict[str, object]],
    status_by_task: dict[str, object] | None = None,
) -> str | None:
    """Render a layered left-to-right SVG from ``[{id, depends_on}]`` dicts.

    Returns None for empty input, oversized graphs (>200 nodes), or cyclic
    dependencies. Status colors are applied when *status_by_task* is given.
    """
    statuses = status_by_task or {}
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
        f'width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#0d1117" rx="8"/>',
        '<defs><marker id="arw" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#58a6ff"/></marker></defs>',
    ]
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
        st = statuses.get(tid)
        fill = _STATUS_FILL.get(str(st), "#161b22") if st else "#161b22"
        stroke = _STATUS_STROKE.get(str(st), "#30363d") if st else "#30363d"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{_NODE_W}" height="{_NODE_H}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        )
        label = escape(tid[:18])
        parts.append(
            f'<text x="{x + _NODE_W / 2}" y="{y + _NODE_H / 2 + 4}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="11.5" fill="#c9d1d9">{label}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
