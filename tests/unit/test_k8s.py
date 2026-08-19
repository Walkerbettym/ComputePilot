"""Tests for Kubernetes and FakeKubernetes executors."""

from __future__ import annotations

import pytest

from computepilot.executors.fake_k8s import FakeKubernetesExecutor
from computepilot.models.run import TaskStatus
from computepilot.models.workflow import Task


@pytest.fixture
def fake_k8s() -> FakeKubernetesExecutor:
    return FakeKubernetesExecutor()


class TestFakeK8sSubmit:
    @pytest.mark.asyncio
    async def test_submit_records_task(self, fake_k8s: FakeKubernetesExecutor) -> None:
        handle = await fake_k8s.submit(Task(id="t1", command="echo"), "/tmp", {})
        assert handle.task_id == "t1"
        assert handle.job_id == "k8s-job-1"
        assert len(fake_k8s.submitted) == 1

    @pytest.mark.asyncio
    async def test_status_always_succeeded(self, fake_k8s: FakeKubernetesExecutor) -> None:
        handle = await fake_k8s.submit(Task(id="t", command="echo"), "/tmp", {})
        assert await fake_k8s.status(handle) == TaskStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_collect_returns_ok(self, fake_k8s: FakeKubernetesExecutor) -> None:
        handle = await fake_k8s.submit(Task(id="t", command="echo"), "/tmp", {})
        result = await fake_k8s.collect(handle)
        assert result.ok
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_cancel_no_error(self, fake_k8s: FakeKubernetesExecutor) -> None:
        handle = await fake_k8s.submit(Task(id="t", command="echo"), "/tmp", {})
        await fake_k8s.cancel(handle)

    @pytest.mark.asyncio
    async def test_logs_empty(self, fake_k8s: FakeKubernetesExecutor) -> None:
        handle = await fake_k8s.submit(Task(id="t", command="echo"), "/tmp", {})
        assert await fake_k8s.logs(handle) == ""

    def test_capability(self, fake_k8s: FakeKubernetesExecutor) -> None:
        cap = fake_k8s.capability()
        assert cap.supports_gpu
        assert cap.isolation == "container"

    def test_validate_task_returns_empty(self, fake_k8s: FakeKubernetesExecutor) -> None:
        assert fake_k8s.validate_task(Task(id="t", command="echo")) == []
