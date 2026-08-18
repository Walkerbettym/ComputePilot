"""Tests for the skill system."""

from __future__ import annotations

from pathlib import Path

from sciflow.skills.base import Skill, SkillRegistry
from sciflow.skills.docker import docker_skill
from sciflow.skills.python import python_skill
from sciflow.skills.shell import shell_skill
from sciflow.skills.slurm import slurm_skill


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
            error_handling={"err": {"action": "retry", "params": {"n": 3}}},
        )
        assert skill.name == "full"
        assert skill.version == "1.0.0"
        assert skill.capabilities == ["a", "b"]
        assert skill.constraints["key"] == "val"
        assert skill.error_handling["err"]["action"] == "retry"

    def test_round_trip_json(self) -> None:
        skill = Skill(
            name="roundtrip",
            capabilities=["run"],
            error_handling={"fail": {"action": "report", "params": {}}},
        )
        data = skill.model_dump()
        restored = Skill.model_validate(data)
        assert restored.name == "roundtrip"
        assert restored.capabilities == ["run"]


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


class TestBuiltinSkills:
    def test_python_skill(self) -> None:
        assert python_skill.name == "python"
        assert "run_python" in python_skill.capabilities
        assert "install_packages" in python_skill.capabilities

    def test_shell_skill(self) -> None:
        assert shell_skill.name == "shell"
        assert "run_shell_command" in shell_skill.capabilities
        assert "pipe_redirect" in shell_skill.capabilities

    def test_slurm_skill(self) -> None:
        assert slurm_skill.name == "slurm"
        assert "submit_batch_job" in slurm_skill.capabilities
        assert "monitor_job" in slurm_skill.capabilities

    def test_docker_skill(self) -> None:
        assert docker_skill.name == "docker"
        assert "run_container" in docker_skill.capabilities
        assert "pull_image" in docker_skill.capabilities


class TestSkillRetriever:
    def test_retrieve_by_name(self) -> None:
        from sciflow.agent.selector import SkillRetriever

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
        from sciflow.agent.selector import SkillRetriever

        registry = SkillRegistry()
        registry.register(shell_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("shell commands", top_k=5)
        assert any(s.name == "shell" for s in results)

    def test_retrieve_returns_top_k(self) -> None:
        from sciflow.agent.selector import SkillRetriever

        registry = SkillRegistry()
        registry.register(python_skill)
        registry.register(shell_skill)
        registry.register(slurm_skill)
        registry.register(docker_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("docker", top_k=1)
        assert len(results) == 1

    def test_retrieve_empty_query(self) -> None:
        from sciflow.agent.selector import SkillRetriever

        registry = SkillRegistry()
        registry.register(python_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("", top_k=5)
        assert len(results) >= 1

    def test_retrieve_no_match(self) -> None:
        from sciflow.agent.selector import SkillRetriever

        registry = SkillRegistry()
        registry.register(python_skill)
        retriever = SkillRetriever(registry)

        results = retriever.retrieve("zzzunknownzzz", top_k=5)
        assert len(results) == 0
