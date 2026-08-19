"""Base skill model and registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from yaml import safe_load

from computepilot.models.workflow import Resources


class ErrorAction(BaseModel):
    """Action to take when a skill encounters a specific error condition."""

    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class Skill(BaseModel):
    """A named capability bundle for a workflow execution environment."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    resources_defaults: Resources = Field(default_factory=Resources)
    error_handling: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of error cause to recovery action and params",
    )


class SkillRegistry:
    """Registry of known skills for task routing and validation."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill by name."""
        self._skills[skill.name] = skill

    def register_builtins(self) -> None:
        """Register all built-in skills."""
        from computepilot.skills.docker import docker_skill
        from computepilot.skills.python import python_skill
        from computepilot.skills.shell import shell_skill
        from computepilot.skills.slurm import slurm_skill

        for skill in (python_skill, shell_skill, slurm_skill, docker_skill):
            self.register(skill)

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """Return all registered skills."""
        return list(self._skills.values())

    def load_from_yaml(self, path: str) -> Skill:
        """Load a skill definition from a YAML file."""
        raw = safe_load(Path(path).read_text(encoding="utf-8"))
        return Skill.model_validate(raw)

    def load_from_path(self, path: str | Path) -> Skill:
        """Load a skill definition from a YAML or JSON file."""
        p = Path(path)
        raw = p.read_text(encoding="utf-8")
        if p.suffix in {".yaml", ".yml"}:
            data = safe_load(raw)
        elif p.suffix == ".json":
            data = json.loads(raw)
        else:
            msg = f"unsupported skill file format: {p.suffix}"
            raise ValueError(msg)
        return Skill.model_validate(data)
