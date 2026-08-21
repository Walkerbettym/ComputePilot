"""Integration tests for ArtifactStore, ProvenanceBuilder, and CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from computepilot.artifacts.provenance import ProvenanceBuilder
from computepilot.artifacts.store import ArtifactStore
from computepilot.models.run import Run, RunStatus
from computepilot.runtime.state import StateStore

# ---------------------------------------------------------------------------
# ArtifactStore
# ---------------------------------------------------------------------------


def test_artifact_store_register(tmp_path: Path) -> None:
    """Register an artifact and verify it is persisted."""
    db = tmp_path / "test.db"
    state = StateStore(db)
    store = ArtifactStore(state)

    # Create a dummy artifact file
    artifact_file = tmp_path / "results.csv"
    artifact_file.write_text("a,b,c\n1,2,3\n")

    meta = store.register(
        run_id="run_001",
        task_id="simulate",
        path=artifact_file,
        artifact_type="text/csv",
    )

    assert meta["id"] != meta["checksum"][:16]  # id is row-unique, not content address
    assert meta["size"] == artifact_file.stat().st_size
    assert meta["path"] == str(artifact_file)

    # Verify it's queryable
    artifacts = store.list_for_run("run_001")
    assert len(artifacts) == 1
    assert artifacts[0]["task_id"] == "simulate"
    assert artifacts[0]["type"] == "text/csv"


def test_artifact_store_list_empty(tmp_path: Path) -> None:
    """list_for_run returns empty list when no artifacts exist."""
    state = StateStore(tmp_path / "empty.db")
    store = ArtifactStore(state)
    assert store.list_for_run("nonexistent") == []


def test_artifact_store_multiple(tmp_path: Path) -> None:
    """Multiple artifacts for the same run are all listed."""
    state = StateStore(tmp_path / "multi.db")
    store = ArtifactStore(state)

    for i in range(3):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"content_{i}")
        store.register("run_002", f"task_{i}", f, "text/plain")

    artifacts = store.list_for_run("run_002")
    assert len(artifacts) == 3
    assert {a["task_id"] for a in artifacts} == {"task_0", "task_1", "task_2"}


# ---------------------------------------------------------------------------
# ProvenanceBuilder
# ---------------------------------------------------------------------------


def test_provenance_build_manifest(tmp_path: Path) -> None:
    """build_manifest returns expected structure."""
    run = Run(
        id="test_run",
        workflow_id=UUID("00000000-0000-0000-0000-000000000001"),
        workflow_name="test_workflow",
        workflow_sha256="abc123",
        status=RunStatus.SUCCEEDED,
        created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    builder = ProvenanceBuilder(run)
    manifest = builder.build_manifest()

    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "test_run"
    assert manifest["workflow"]["name"] == "test_workflow"
    assert manifest["workflow"]["sha256"] == "abc123"
    assert manifest["code"]["type"] in ("git", "unknown")
    assert manifest["parameters"] == {}
    assert manifest["artifacts"] == []


def test_provenance_write_manifest(tmp_path: Path) -> None:
    """write_manifest creates a valid JSON file."""
    run = Run(
        id="test_run",
        workflow_id=UUID("00000000-0000-0000-0000-000000000002"),
        workflow_name="write_test",
        workflow_sha256="def456",
        status=RunStatus.SUCCEEDED,
        created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    builder = ProvenanceBuilder(run)
    out = tmp_path / "manifest.json"
    result = builder.write_manifest(out)

    assert result == out
    assert out.exists()

    data = json.loads(out.read_text())
    assert data["run_id"] == "test_run"
    assert data["workflow"]["name"] == "write_test"


# ---------------------------------------------------------------------------
# ProvenanceBuilder : git detection
# ---------------------------------------------------------------------------


def test_provenance_git_detection(tmp_path: Path) -> None:
    """ProvenanceBuilder detects git commit when in a git repo."""
    # Initialize a git repo in tmp_path
    import subprocess

    from computepilot.artifacts.provenance import ProvenanceBuilder

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("# test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
    )

    # Temporarily change to tmp_path to detect git
    import os

    orig_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        version = ProvenanceBuilder._detect_code_version()
        assert version["type"] == "git"
        assert len(version["commit"]) == 40  # full SHA
    finally:
        os.chdir(orig_cwd)
