"""Workflow YAML serialization and deserialization."""

from pathlib import Path

import yaml

from sciflow.models.workflow import Workflow


def load_workflow(path: str | Path) -> Workflow:
    """Parse workflow.yaml → Workflow with line-number error reporting."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    # Build Workflow model; Pydantic validation catches field errors
    return Workflow(**raw, source=path)


def dump_workflow(wf: Workflow) -> str:
    """Serialize Workflow → YAML string."""
    data = wf.model_dump(
        exclude={"id", "sha256", "source", "created_at"}, mode="json"
    )
    return yaml.dump(data, default_flow_style=False, sort_keys=False)
