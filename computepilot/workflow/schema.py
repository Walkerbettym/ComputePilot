"""Workflow YAML serialization and deserialization."""

from pathlib import Path
from typing import Any

import yaml

from computepilot.models.workflow import Workflow
from computepilot.workflow.params import substitute_workflow_data


def load_workflow(path: str | Path, params: dict[str, str] | None = None) -> Workflow:
    """Parse workflow.yaml → Workflow with line-number error reporting.

    *params* values replace ``${key}`` / ``${key:-default}`` placeholders
    before model validation, so downstream rules see final values.
    """
    path = Path(path)
    raw: Any = yaml.safe_load(path.read_text())
    if params is not None:
        raw = substitute_workflow_data(raw, params)
    # Build Workflow model; Pydantic validation catches field errors
    return Workflow(**raw, source=path)


def dump_workflow(wf: Workflow) -> str:
    """Serialize Workflow → YAML string."""
    data = wf.model_dump(exclude={"id", "sha256", "source", "created_at"}, mode="json")
    return yaml.dump(data, default_flow_style=False, sort_keys=False)
