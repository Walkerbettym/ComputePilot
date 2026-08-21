"""Skill system — executable capability definitions for workflow tasks."""

from computepilot.skills.base import Skill, SkillRegistry
from computepilot.skills.docker import docker_skill
from computepilot.skills.gromacs import gromacs_skill
from computepilot.skills.lammps import lammps_skill
from computepilot.skills.openfoam import openfoam_skill
from computepilot.skills.python import python_skill
from computepilot.skills.shell import shell_skill
from computepilot.skills.slurm import slurm_skill

__all__ = [
    "Skill",
    "SkillRegistry",
    "docker_skill",
    "gromacs_skill",
    "lammps_skill",
    "openfoam_skill",
    "python_skill",
    "shell_skill",
    "slurm_skill",
]
