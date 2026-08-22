from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class TaskType(StrEnum):
    PYTHON = "python"
    SHELL = "shell"
    DOCKER = "docker"
    SLURM = "slurm"


class Resources(BaseModel):
    cpu: int = 1
    memory: str = "2GB"
    gpu: int = 0
    partition: str | None = None
    walltime: timedelta | None = None

    @field_validator("cpu")
    @classmethod
    def cpu_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("cpu must be >= 1")
        return v

    @field_validator("gpu")
    @classmethod
    def gpu_nonnegative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("gpu must be >= 0")
        return v

    @field_validator("memory")
    @classmethod
    def memory_parseable(cls, v: str) -> str:
        # Accept: 512MB, 2GB, 4GiB, etc.
        if not re.match(r"^\d+\s*(MB|MiB|GB|GiB|TB|TiB)$", v.strip()):
            raise ValueError(f"memory format not parseable: {v}")
        return v.strip()


class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff: Literal["none", "fixed", "exponential"] = "exponential"
    base_delay: timedelta = timedelta(seconds=5)
    max_delay: timedelta = timedelta(seconds=300)
    retryable_exit_codes: list[int] = [1, 2, 137]
    retryable_signals: list[str] = []

    @field_validator("max_attempts")
    @classmethod
    def attempts_in_range(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_attempts must be 1..10")
        return v


class Task(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
    type: TaskType = TaskType.PYTHON
    command: str
    args: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []
    depends_on: list[str] = []
    resources: Resources = Resources()
    environment: dict[str, str] = {}
    image: str | None = None
    volumes: list[str] = []
    retry_policy: RetryPolicy = RetryPolicy()
    priority: int = 0
    timeout: timedelta | None = None
    checkpoint: bool = True
    tags: dict[str, str] = {}
    metadata: dict[str, Any] = {}


class PartialTask(BaseModel):
    """Task with all fields optional, used for Workflow.defaults."""

    id: str | None = None
    type: TaskType | None = None
    command: str | None = None
    args: list[str] | None = None
    inputs: list[str] | None = None
    outputs: list[str] | None = None
    depends_on: list[str] | None = None
    resources: Resources | None = None
    environment: dict[str, str] | None = None
    image: str | None = None
    volumes: list[str] | None = None
    retry_policy: RetryPolicy | None = None
    timeout: timedelta | None = None
    checkpoint: bool | None = None
    tags: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None


class Workflow(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    description: str | None = None
    version: str = "0.1.0"
    schema_version: int = 1
    source: Path | None = None
    sha256: str = ""
    variables: dict[str, str | int | float] = {}
    env: dict[str, str] = {}
    defaults: PartialTask | None = None
    tasks: list[Task] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    notifications: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional callbacks: {'on_failed'/'on_succeeded': {'url': ..., "
            "'timeout': seconds}}. Engine POSTs run outcome JSON to the URL."
        ),
    )

    @field_validator("tasks")
    @classmethod
    def unique_task_ids(cls, tasks: list[Task]) -> list[Task]:
        ids = [t.id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate task ids: {[id for id in ids if ids.count(id) > 1]}")
        return tasks
