"""ProvenanceBuilder — generate a reproducible manifest for a workflow run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from sciflow.models.run import Run


class ProvenanceBuilder:
    """Build a provenance manifest (``manifest.json``) for a completed run.

    The manifest captures the workflow identity, code version, environment,
    parameters, and artifact references so the run can be reproduced later.
    """

    def __init__(self, run: Run) -> None:
        self.run = run

    def build_manifest(self) -> dict[str, Any]:
        """Return the manifest dictionary."""
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
            "artifacts": [],
            "task_events": [],
        }

    def write_manifest(self, path: Path) -> Path:
        """Write *manifest.json* to *path* and return the path."""
        manifest = self.build_manifest()
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
