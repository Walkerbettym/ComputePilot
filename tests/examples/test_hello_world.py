"""Tests for example workflows — verifies they are valid and runnable."""

from __future__ import annotations

from pathlib import Path

from computepilot.workflow.schema import load_workflow
from computepilot.workflow.validator import validate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


def test_hello_world_valid() -> None:
    """examples/hello_world/workflow.yaml is valid."""
    path = EXAMPLES_DIR / "hello_world" / "workflow.yaml"
    assert path.exists(), f"Example not found: {path}"

    wf = load_workflow(path)
    report = validate(wf)
    assert report.passed, f"Validation errors: {report.errors}"

    assert wf.name == "hello_world"
    assert len(wf.tasks) == 1
    assert wf.tasks[0].id == "greet"
    assert wf.tasks[0].type.value == "shell"
