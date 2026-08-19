"""Executors for running tasks locally or on remote clusters."""

from computepilot.executors.docker import DockerExecutor
from computepilot.executors.fake_slurm import FakeSlurmExecutor
from computepilot.executors.local import LocalExecutor
from computepilot.executors.slurm import SlurmExecutor

__all__ = ["DockerExecutor", "FakeSlurmExecutor", "LocalExecutor", "SlurmExecutor"]
