"""Workflow YAML serialization and deserialization."""

from pathlib import Path
from typing import Any

import yaml

from computepilot.models.workflow import Workflow
from computepilot.workflow.expand import expand_foreach
from computepilot.workflow.params import substitute_workflow_data

_MAX_INCLUDE_DEPTH = 16


class IncludeError(ValueError):
    """Raised for include cycles or duplicate task ids across includes."""


def _merge_includes(raw: dict[str, Any], base_dir: Path, stack: tuple[Path, ...]) -> dict[str, Any]:
    """Recursively inline ``includes:`` lists; returns raw data with merged tasks."""
    if len(stack) > _MAX_INCLUDE_DEPTH:
        raise IncludeError("include depth exceeded (possible cycle)")

    merged: list[dict[str, Any]] = []
    for inc in raw.pop("includes", []) or []:
        path = (base_dir / str(inc)).resolve()
        if path in stack:
            chain = " -> ".join(str(p) for p in (*stack, path))
            raise IncludeError(f"include cycle detected: {chain}")
        sub_raw = yaml.safe_load(path.read_text())
        if not isinstance(sub_raw, dict):
            raise IncludeError(f"include is not a mapping: {path}")
        sub_raw = _merge_includes(sub_raw, path.parent, (*stack, path))
        merged.extend(sub_raw.get("tasks") or [])

    own = raw.get("tasks") or []
    tasks = merged + list(own)
    ids = [str(t.get("id")) for t in tasks if isinstance(t, dict) and t.get("id")]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise IncludeError(f"duplicate task id(s) after includes: {', '.join(dupes)}")
    raw["tasks"] = tasks
    return raw


def load_workflow(path: str | Path, params: dict[str, str] | None = None) -> Workflow:
    """Parse workflow.yaml → Workflow with line-number error reporting.

    *params* values replace ``${key}`` / ``${key:-default}`` placeholders
    before model validation, so downstream rules see final values.
    Top-level ``includes:`` are merged recursively before validation.
    """
    path = Path(path)
    raw: Any = yaml.safe_load(path.read_text())
    raw = _merge_includes(raw, path.parent, (path.resolve(),))
    raw = expand_foreach(raw)
    if params is not None:
        raw = substitute_workflow_data(raw, params)
    # Build Workflow model; Pydantic validation catches field errors
    return Workflow(**raw, source=path)


def dump_workflow(wf: Workflow) -> str:
    """Serialize Workflow → YAML string."""
    data = wf.model_dump(exclude={"id", "sha256", "source", "created_at"}, mode="json")
    return yaml.dump(data, default_flow_style=False, sort_keys=False)
