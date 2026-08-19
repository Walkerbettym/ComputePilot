"""Tests for the skill system — Skill model, SkillRegistry, SkillRetriever."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from computepilot.agent.selector import SkillRetriever
from computepilot.models.workflow import Resources
from computepilot.skills.base import ErrorAction, Skill, SkillRegistry
from computepilot.skills.docker import docker_skill
from computepilot.skills.python import python_skill
from computepilot.skills.shell import shell_skill
from computepilot.skills.slurm import slurm_skill


class TestSkillModel:
    def test_minimal_skill(self) -> None:
        skill = Skill(name="test")
        assert skill.name == "test"
        assert skill.version == "0.1.0"
        assert skill.description == ""
        assert skill.capabilities == []

    def test_full_skill(self) -> None:
        skill = Skill(
            name="full",
            version="1.0.0",
            description="A full skill",
            capabilities=["a", "b"],
            constraints={"key": "val"},
            resources_defaults=Resources(cpu=2, memory="4GB"),
            error_handling={
                "err": ErrorAction(action="retry", params={"n": 3}),
            },
        )
        assert skill.name == "full"
        assert skill.version == "1.0.0"
        assert skill.capabilities == ["a", "b"]
        assert skill.constraints["key"] == "val"
        assert skill.resources_defaults.cpu == 2
        assert skill.resources_defaults.memory == "4GB"
        assert skill.error_handling["err"].action == "retry"
        assert skill.error_handling["err"].params == {"n": 3}

    def test_round_trip_json(self) -> None:
        skill = Skill(
            name="roundtrip",
            capabilities=["run"],
            error_handling={
                "fail": ErrorAction(action="report", params={}),
            },
        )
        data = skill.model_dump()
        restored = Skill.model_validate(data)
        assert restored.name == "roundtrip"
        assert restored.capabilities == ["run"]
        assert restored.error_handling["fail"]["action"] == "report"

    def test_skill_name_required(self) -> None:
        with pytest.raises(ValidationError):
            Skill()  # type: ignore[call-arg]

    def test_error_action_minimal(self) -> None:
        ea = ErrorAction(action="retry")
        assert ea.action == "retry"
        assert ea.params == {}

    def test_error_action_full(self) -> None:
        ea = ErrorAction(action="increase_memory", params={"factor": 2.0})
        assert ea.action == "increase_memory"
        assert ea.params == {"factor": 2.0}


class TestSkillRegistry:
    def test_register_and_get(self) -> None:
        registry = SkillRegistry()
        skill = Skill(name="alpha")
        registry.register(skill)
        assert registry.get("alpha") is skill
        assert registry.get("nonexistent") is None

    def test_list_all(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(name="a"))
        registry.register(Skill(name="b"))
        assert len(registry.list_all()) == 2

    def test_register_overwrites(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(name="dup", version="1.0.0"))
        registry.register(Skill(name="dup", version="2.0.0"))
        assert registry.get("dup") is not None
        assert registry.get("dup").version == "2.0.0"  # type: ignore[union-attr]

    def test_register_builtins(self) -> None:
        registry = SkillRegistry()
        registry.register_builtins()
        names = {s.name for s in registry.list_all()}
        assert names == {"python", "shell", "slurm", "docker", "population_genetics"}

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
name: yaml-skill
version: "1.2.3"
description: Loaded from YAML
capabilities:
  - do_thing
constraints:
  x: 1
error_handling:
  err:
    action: report
    params: {}
"""
        path = tmp_path / "skill.yaml"
        path.write_text(yaml_content)

        registry = SkillRegistry()
        skill = registry.load_from_yaml(str(path))
        assert skill.name == "yaml-skill"
        assert skill.version == "1.2.3"
        assert skill.capabilities == ["do_thing"]
        assert skill.constraints["x"] == 1

    def test_load_from_path_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "skill.yaml"
        path.write_text(yaml.dump({"name": "from_path", "capabilities": ["run"]}))
        registry = SkillRegistry()
        skill = registry.load_from_path(path)
        assert skill.name == "from_path"

    def test_load_from_path_json(self, tmp_path: Path) -> None:
        path = tmp_path / "skill.json"
        path.write_text(json.dumps({"name": "from_json", "capabilities": ["run"]}))
        registry = SkillRegistry()
        skill = registry.load_from_path(path)
        assert skill.name == "from_json"

    def test_load_from_path_unsupported(self, tmp_path: Path) -> None:
        path = tmp_path / "skill.txt"
        path.write_text("hello")
        registry = SkillRegistry()
        with pytest.raises(ValueError, match="unsupported"):
            registry.load_from_path(path)


class TestBuiltinSkills:
    def test_python_skill(self) -> None:
        assert python_skill.name == "python"
        assert "run_python" in python_skill.capabilities
        assert "run_script" in python_skill.capabilities

    def test_shell_skill(self) -> None:
        assert shell_skill.name == "shell"
        assert "run_shell_command" in shell_skill.capabilities
        assert "pipe_redirect" in shell_skill.capabilities

    def test_slurm_skill(self) -> None:
        assert slurm_skill.name == "slurm"
        assert "submit_batch_job" in slurm_skill.capabilities
        assert "monitor_job" in slurm_skill.capabilities
        assert "job_failed" in slurm_skill.error_handling

    def test_docker_skill(self) -> None:
        assert docker_skill.name == "docker"
        assert "run_container" in docker_skill.capabilities
        assert "pull_image" in docker_skill.capabilities


class TestSkillVocabulary:
    """Tests for skill vocabulary resolution (v0.2)."""

    def test_resolve_vocabulary_direct_match(self) -> None:
        """Direct token resolution works."""
        skill = Skill(
            name="genomics",
            vocabulary_mappings={
                "population": {"european": "EUR", "african": "AFR"},
                "region": {"chromosome 22": "chr22", "chromosome 1": "chr1"},
            },
        )
        assert skill.resolve_vocabulary("european") == "EUR"
        assert skill.resolve_vocabulary("african") == "AFR"
        assert skill.resolve_vocabulary("chromosome 22") == "chr22"

    def test_resolve_vocabulary_case_insensitive(self) -> None:
        """Resolution is case-insensitive."""
        skill = Skill(
            name="genomics",
            vocabulary_mappings={"population": {"european": "EUR"}},
        )
        assert skill.resolve_vocabulary("European") == "EUR"
        assert skill.resolve_vocabulary("EUROPEAN") == "EUR"

    def test_resolve_vocabulary_no_match(self) -> None:
        """Unmatched tokens return None."""
        skill = Skill(name="genomics", vocabulary_mappings={})
        assert skill.resolve_vocabulary("nonexistent") is None

    def test_resolve_vocabulary_filtered_field(self) -> None:
        """Field filter restricts resolution."""
        skill = Skill(
            name="genomics",
            vocabulary_mappings={
                "population": {"european": "EUR"},
                "region": {"chromosome 22": "chr22"},
            },
        )
        assert skill.resolve_vocabulary("european", field="region") is None
        assert skill.resolve_vocabulary("chromosome 22", field="region") == "chr22"

    def test_vocabulary_mappings_yaml_roundtrip(self, tmp_path: Path) -> None:
        """Skill with vocabulary can be serialized to YAML and back."""
        skill = Skill(
            name="genomics",
            vocabulary_mappings={
                "population": {"european": "EUR", "african": "AFR"},
            },
            parameter_constraints={
                "chromosomes": {"allowed": ["1", "22"], "required": True},
            },
            optimization_strategies=["selective_data_extraction"],
        )
        from computepilot.skills.base import Skill as SkillImport

        raw = skill.model_dump()
        restored = SkillImport.model_validate(raw)
        assert restored.name == "genomics"
        assert restored.vocabulary_mappings["population"]["european"] == "EUR"
        assert restored.parameter_constraints["chromosomes"]["allowed"] == ["1", "22"]
        assert restored.optimization_strategies == ["selective_data_extraction"]


class TestSkillRetriever:
    def test_retrieve_by_name(self) -> None:
        registry = SkillRegistry()
        registry.register(python_skill)
        registry.register(shell_skill)
        registry.register(slurm_skill)
        registry.register(docker_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("python", top_k=2)
        assert len(results) >= 1
        assert results[0].name == "python"

    def test_retrieve_by_description(self) -> None:
        registry = SkillRegistry()
        registry.register(shell_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("shell commands", top_k=5)
        assert any(s.name == "shell" for s in results)

    def test_retrieve_returns_top_k(self) -> None:
        registry = SkillRegistry()
        registry.register(python_skill)
        registry.register(shell_skill)
        registry.register(slurm_skill)
        registry.register(docker_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("docker", top_k=1)
        assert len(results) == 1

    def test_retrieve_empty_query(self) -> None:
        registry = SkillRegistry()
        registry.register(python_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("", top_k=5)
        assert len(results) >= 1

    def test_retrieve_no_match(self) -> None:
        registry = SkillRegistry()
        registry.register(python_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("zzzunknownzzz", top_k=5)
        assert len(results) == 0

    def test_for_task(self) -> None:
        registry = SkillRegistry()
        registry.register_builtins()
        retriever = SkillRetriever(registry)

        results = retriever.for_task("python")
        assert len(results) == 1
        assert results[0].name == "python"

        results = retriever.for_task("slurm")
        assert len(results) == 1
        assert results[0].name == "slurm"

    def test_for_capability(self) -> None:
        registry = SkillRegistry()
        registry.register_builtins()
        retriever = SkillRetriever(registry)

        results = retriever.for_capability("run_python")
        assert len(results) == 1
        assert results[0].name == "python"

        results = retriever.for_capability("run_shell_command")
        assert len(results) == 1
        assert results[0].name == "shell"

    def test_for_capability_no_match(self) -> None:
        registry = SkillRegistry()
        registry.register_builtins()
        retriever = SkillRetriever(registry)

        results = retriever.for_capability("nonexistent_capability")
        assert results == []

    def test_registry_property(self) -> None:
        registry = SkillRegistry()
        retriever = SkillRetriever(registry)
        assert retriever.registry is registry
