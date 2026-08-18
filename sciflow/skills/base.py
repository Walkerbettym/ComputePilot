"""Base skill model and registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from yaml import safe_load


class Skill(BaseModel):
    """A named capability bundle for a workflow execution environment."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
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
