"""Skill system — executable capability definitions for workflow tasks."""

from sciflow.skills.base import Skill, SkillRegistry
from sciflow.skills.docker import docker_skill
from sciflow.skills.python import python_skill
from sciflow.skills.shell import shell_skill
from sciflow.skills.slurm import slurm_skill

__all__ = [
    "Skill",
    "SkillRegistry",
    "docker_skill",
    "python_skill",
    "shell_skill",
    "slurm_skill",
]
