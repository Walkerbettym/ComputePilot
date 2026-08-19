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
    """A named capability bundle for a workflow execution environment.

    Aligned with the paper's knowledge layer: skills encode
    vocabulary mappings, parameter constraints, and optimization
    strategies as persistent, auditable artifacts.
    """

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
    # -- Paper-aligned knowledge-layer extensions (v0.2) --
    vocabulary_mappings: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description=(
            "Domain vocabulary mappings, e.g. "
            "{'population': {'european': 'EUR', 'african': 'AFR'}}. "
            "Natural-language tokens are canonicalized to domain codes."
        ),
    )
    parameter_constraints: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Constraints on task parameters, e.g. "
            "{'chromosomes': {'allowed': ['1', '22'], 'required': True}}."
        ),
    )
    optimization_strategies: list[str] = Field(
        default_factory=list,
        description=(
            "Execution-time optimization hints, e.g. "
            "['selective_data_extraction', 'parallelism_autotune']."
        ),
    )

    def resolve_vocabulary(self, token: str, field: str | None = None) -> str | None:
        """Resolve a natural-language token to a domain code.

        Returns the matched code if found in ``vocabulary_mappings``,
        otherwise ``None``.
        """
        token_lower = token.strip().lower()
        for field_name, mappings in self.vocabulary_mappings.items():
            if field is not None and field_name != field:
                continue
            canonical = mappings.get(token_lower)
            if canonical is not None:
                return canonical
        return None


class SkillRegistry:
    """Registry of known skills for task routing and validation."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill by name."""
        self._skills[skill.name] = skill

    def register_builtins(self) -> None:
        """Register all built-in skills (v0.2: includes population_genetics)."""
        from computepilot.skills.docker import docker_skill
        from computepilot.skills.population_genetics import population_genetics_skill
        from computepilot.skills.python import python_skill
        from computepilot.skills.shell import shell_skill
        from computepilot.skills.slurm import slurm_skill

        for skill in (
            python_skill,
            shell_skill,
            slurm_skill,
            docker_skill,
            population_genetics_skill,
        ):
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
