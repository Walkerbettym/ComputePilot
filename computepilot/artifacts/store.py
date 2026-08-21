"""ArtifactStore — register and query run artifacts backed by the SQLite state store."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from computepilot.runtime.state import StateStore


class ArtifactStore:
    """Persist artifact metadata (checksum, size, type) for a workflow run."""

    def __init__(self, state: StateStore) -> None:
        self.state = state

    def register(
        self,
        run_id: str,
        task_id: str,
        path: str | Path,
        artifact_type: str,
    ) -> dict[str, Any]:
        """Register an artifact and return its metadata dict.

        Parameters
        ----------
        run_id:
            The run this artifact belongs to.
        task_id:
            The task that produced the artifact.
        path:
            Filesystem path to the artifact file.
        artifact_type:
            MIME-like type string (e.g. ``"text/csv"``, ``"image/png"``).

        Returns
        -------
        dict with keys ``id``, ``path``, ``checksum``, ``size``.
        """
        p = Path(path)
        checksum = hashlib.sha256(p.read_bytes()).hexdigest()
        size = p.stat().st_size
        aid = hashlib.sha256(f"{run_id}:{p}:{checksum}".encode()).hexdigest()[:16]

        self.state._conn.execute(
            "INSERT INTO artifacts (id, run_id, task_id, path, type, checksum, size, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                aid,
                run_id,
                task_id,
                str(p),
                artifact_type,
                checksum,
                size,
                datetime.now().isoformat(),
            ),
        )
        self.state._conn.commit()

        return {"id": aid, "path": str(p), "checksum": checksum, "size": size}

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Return all artifacts registered for *run_id*."""
        rows = self.state._conn.execute(
            "SELECT id, task_id, path, type, checksum, size, created_at "
            "FROM artifacts WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
