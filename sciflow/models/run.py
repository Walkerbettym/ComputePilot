from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    RESUMING = "resuming"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Run(BaseModel):
    id: str
    workflow_id: UUID
    workflow_sha256: str
    status: RunStatus = RunStatus.CREATED
    executor: str = "local"
    config: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_dir: Path | None = None
    metrics: dict[str, Any] = {}
