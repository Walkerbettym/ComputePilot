"""Executors for running tasks locally or on remote clusters."""

from sciflow.executors.docker import DockerExecutor
from sciflow.executors.fake_slurm import FakeSlurmExecutor
from sciflow.executors.local import LocalExecutor
from sciflow.executors.slurm import SlurmExecutor

__all__ = ["DockerExecutor", "FakeSlurmExecutor", "LocalExecutor", "SlurmExecutor"]
