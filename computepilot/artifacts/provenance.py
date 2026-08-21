"""ProvenanceBuilder — generate a reproducible manifest for a workflow run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from computepilot.models.run import Run


class ProvenanceBuilder:
    """Build a provenance manifest (``manifest.json``) for a completed run.

    The manifest captures the workflow identity, code version, environment,
    parameters, and artifact references so the run can be reproduced later.
    """

    def __init__(self, run: Run) -> None:
        self.run = run

    def build_manifest(self, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Return the manifest dictionary.

        *artifacts* takes ``ArtifactStore.list_for_run`` rows; each is
        normalized to an auditable reference with its checksum.
        """
        return {
            "schema_version": 1,
            "run_id": self.run.id,
            "workflow": {
                "sha256": self.run.workflow_sha256,
                "name": self.run.workflow_name,
            },
            "code": self._detect_code_version(),
            "environment": {"type": "unknown"},
            "parameters": {},
            "artifacts": [self._artifact_ref(a) for a in (artifacts or [])],
            "task_events": [],
        }

    @staticmethod
    def _artifact_ref(artifact: dict[str, Any]) -> dict[str, Any]:
        """Normalize one artifact row into a manifest artifact reference."""
        return {
            "id": str(artifact.get("id", "")),
            "task_id": artifact.get("task_id"),
            "path": str(artifact.get("path", "")),
            "type": str(artifact.get("type", "")),
            "sha256": str(artifact.get("checksum", "")),
            "size": int(artifact.get("size") or 0),
        }

    def write_manifest(self, path: Path, artifacts: list[dict[str, Any]] | None = None) -> Path:
        """Write *manifest.json* to *path* and return the path."""
        manifest = self.build_manifest(artifacts)
        path.write_text(json.dumps(manifest, indent=2))
        return path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_code_version() -> dict[str, Any]:
        """Detect the Git commit SHA of the current working tree."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {"type": "git", "commit": result.stdout.strip(), "dirty": False}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return {"type": "unknown"}
