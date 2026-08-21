"""Workspace management — multi-project workspaces for ComputePilot.

A workspace is a directory containing workflows, runs, skills, and state.
Users can create, list, and switch between workspaces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE_ENV = "COMPUTEPILOT_WORKSPACE"


@dataclass
class Workspace:
    """A named workspace with associated metadata."""

    name: str
    path: str
    created_at: str = ""
    last_used: str = ""
    description: str = ""


class WorkspaceManager:
    """Manage ComputePilot workspaces.

    Workspaces are stored in ``~/.local/share/computepilot/workspaces.json``.
    """

    def __init__(self) -> None:
        self._home = Path.home() / ".local" / "share" / "computepilot"
        self._home.mkdir(parents=True, exist_ok=True)
        self._db = self._home / "workspaces.json"
        self._workspaces: dict[str, Workspace] = {}
        self._active: str | None = None
        self._load()

    # -- Public API ---------------------------------------------------------------

    @property
    def active(self) -> str | None:
        """Name of the active workspace, or None."""
        return self._active

    @property
    def active_path(self) -> Path | None:
        """Path to the active workspace directory, or None."""
        if self._active is None:
            return None
        ws = self._workspaces.get(self._active)
        return Path(ws.path) if ws else None

    @property
    def list(self) -> list[Workspace]:
        """All registered workspaces."""
        return list(self._workspaces.values())

    def create(self, name: str, path: str | None = None, description: str = "") -> Workspace:
        """Create a new workspace."""
        if name in self._workspaces:
            msg = f"Workspace '{name}' already exists"
            raise ValueError(msg)

        ws_path = Path(path) if path else self._home / "workspaces" / name
        ws_path.mkdir(parents=True, exist_ok=True)

        now = datetime.now(tz=UTC).isoformat()
        meta = dict(name=name, path=str(ws_path), created_at=now, last_used=now)
        if description:
            meta["description"] = description
        ws = Workspace(**meta)
        self._workspaces[name] = ws
        self._active = name
        self._save()
        return ws

    def get(self, name: str) -> Workspace | None:
        """Get a workspace by name."""
        return self._workspaces.get(name)

    def switch(self, name: str) -> Workspace | None:
        """Switch active workspace. Returns the workspace or None."""
        ws = self._workspaces.get(name)
        if ws:
            self._active = name
            ws.last_used = datetime.now(tz=UTC).isoformat()
            self._save()
        return ws

    def remove(self, name: str) -> bool:
        """Remove a workspace from the registry (does not delete files)."""
        if name not in self._workspaces:
            return False
        del self._workspaces[name]
        if self._active == name:
            self._active = next(iter(self._workspaces)) if self._workspaces else None
        self._save()
        return True

    # -- Internal -----------------------------------------------------------------

    def _load(self) -> None:
        if not self._db.exists():
            return
        try:
            data = json.loads(self._db.read_text())
            self._workspaces = {k: Workspace(**v) for k, v in data.get("workspaces", {}).items()}
            self._active = data.get("active")
        except (json.JSONDecodeError, KeyError, TypeError):
            self._workspaces = {}
            self._active = None

    def _save(self) -> None:
        data = {
            "active": self._active,
            "workspaces": {k: ws.__dict__ for k, ws in self._workspaces.items()},
        }
        self._db.write_text(json.dumps(data, indent=2))
