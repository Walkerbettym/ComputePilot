from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class Manifest(BaseModel):
    """Verification manifest for a workflow artifact."""

    sha256: str
    size: int
    content_type: str = "application/octet-stream"


class ArtifactRef(BaseModel):
    """Reference to an artifact produced or consumed by a task."""

    name: str
    path: Path
    manifest: Manifest | None = None
