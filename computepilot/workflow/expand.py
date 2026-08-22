"""``foreach`` task fan-out — expand one templated task into N concrete tasks."""

from __future__ import annotations

from typing import Any

from computepilot.workflow.params import substitute_partial

_MAX_FANOUT = 500


class ForeachError(ValueError):
    """Raised for invalid foreach blocks or fan-out over the limit."""


def _expand_task(
    task: dict[str, Any], base_id: str, values: list[Any], var: str
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for i, value in enumerate(values):
        item = {k: v for k, v in task.items() if k != "foreach"}
        item["id"] = f"{base_id}_{i}"
        params = {var: str(value)}
        for field in ("command", "args", "inputs", "outputs"):
            raw = item.get(field)
            if isinstance(raw, str):
                item[field] = substitute_partial(raw, params)
            elif isinstance(raw, list):
                item[field] = [
                    substitute_partial(str(x), params) if isinstance(x, str) else x for x in raw
                ]
        env = item.get("environment")
        if isinstance(env, dict):
            item["environment"] = {
                k: (substitute_partial(str(v), params) if isinstance(v, str) else v)
                for k, v in env.items()
            }
        expanded.append(item)
    return expanded


def expand_foreach(raw: dict[str, Any]) -> dict[str, Any]:
    """Expand ``foreach:`` task templates in raw workflow data.

    Runs after include merging and parameter substitution, so ``values``
    entries may reference ``${params}`` and each instance receives the
    ``as`` variable in all string fields.

    A plain ``depends_on: [<base>]`` referencing an expanding template is
    rewritten to depend on every expanded instance.
    """
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        return raw

    templates: dict[str, dict[str, Any]] = {}
    for t in tasks:
        if isinstance(t, dict) and isinstance(t.get("foreach"), dict):
            base = str(t.get("id", ""))
            if not base:
                raise ForeachError("foreach task is missing 'id'")
            templates[base] = t

    if not templates:
        return raw

    out: list[dict[str, Any]] = []
    total_added = 0
    expansions: dict[str, list[str]] = {}

    for t in tasks:
        if not isinstance(t, dict):
            out.append(t)
            continue
        tid = str(t.get("id", ""))
        fe = t.get("foreach") if tid in templates else None
        if fe is None:
            out.append(t)
            continue

        values = fe.get("values")
        var = str(fe.get("as", "item"))
        if not isinstance(values, list) or not values:
            raise ForeachError(f"foreach '{tid}' requires a non-empty 'values' list")
        if total_added + len(values) > _MAX_FANOUT:
            raise ForeachError(
                f"foreach fan-out exceeds {_MAX_FANOUT} tasks "
                f"({total_added} already expanded, need {len(values)} more)"
            )
        instances = _expand_task(t, tid, values, var)
        total_added += len(instances)
        expansions[tid] = [str(x["id"]) for x in instances]
        out.extend(instances)

    # Rewrite depends_on entries that referenced a template base id
    for t in out:
        deps = t.get("depends_on")
        if not isinstance(deps, list):
            continue
        rewritten: list[Any] = []
        for d in deps:
            rewritten.extend(expansions.get(str(d), [d]))
        t["depends_on"] = rewritten

    raw["tasks"] = out
    return raw
