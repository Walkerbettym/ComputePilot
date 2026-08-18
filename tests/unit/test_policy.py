"""Tests for PolicyEngine — resource limits and approval gates."""

from __future__ import annotations

from sciflow.policy.engine import PolicyConfig, PolicyEngine


class TestPolicyConfig:
    """Unit tests for PolicyConfig."""

    def test_defaults(self) -> None:
        cfg = PolicyConfig()
        assert cfg.max_cpu == 128
        assert cfg.max_gpu == 8
        assert cfg.max_estimated_cost_usd == 100.0
        assert "task_count > 1000" in cfg.require_approval_if

    def test_custom_values(self) -> None:
        cfg = PolicyConfig(max_cpu=64, max_gpu=0, max_estimated_cost_usd=50.0)
        assert cfg.max_cpu == 64
        assert cfg.max_gpu == 0
        assert cfg.max_estimated_cost_usd == 50.0

    def test_round_trip_json(self) -> None:
        cfg = PolicyConfig(max_cpu=256, max_gpu=16, max_estimated_cost_usd=200.0)
        data = cfg.model_dump()
        restored = PolicyConfig.model_validate(data)
        assert restored.max_cpu == 256
        assert restored.max_gpu == 16


class TestPolicyEngine:
    """Unit tests for PolicyEngine."""

    def setup_method(self) -> None:
        self.engine = PolicyEngine()

    # --- requires_approval ---

    def test_no_approval_needed(self) -> None:
        assert not self.engine.requires_approval(
            task_count=10, total_cpu=8, has_gpu=False, command="python train.py"
        )

    def test_approval_high_task_count(self) -> None:
        assert self.engine.requires_approval(
            task_count=1000, total_cpu=8, has_gpu=False, command="python train.py"
        )

    def test_approval_high_cpu(self) -> None:
        assert self.engine.requires_approval(
            task_count=10, total_cpu=256, has_gpu=False, command="python train.py"
        )

    def test_approval_rm_rf(self) -> None:
        assert self.engine.requires_approval(
            task_count=10, total_cpu=8, has_gpu=False, command="rm -rf /data"
        )

    def test_approval_gpu_when_max_gpu_zero(self) -> None:
        engine = PolicyEngine(config=PolicyConfig(max_gpu=0))
        assert engine.requires_approval(
            task_count=10, total_cpu=8, has_gpu=True, command="python train.py"
        )

    def test_approval_gpu_ok_when_max_gpu_nonzero(self) -> None:
        assert not self.engine.requires_approval(
            task_count=10, total_cpu=8, has_gpu=True, command="python train.py"
        )

    # --- check_resource_limits ---

    def test_no_violations(self) -> None:
        violations = self.engine.check_resource_limits(cpu=8, gpu=1, estimated_cost_usd=50.0)
        assert violations == []

    def test_cpu_violation(self) -> None:
        violations = self.engine.check_resource_limits(cpu=256, gpu=1, estimated_cost_usd=50.0)
        assert len(violations) == 1
        assert "CPU" in violations[0]

    def test_gpu_violation(self) -> None:
        violations = self.engine.check_resource_limits(cpu=8, gpu=16, estimated_cost_usd=50.0)
        assert len(violations) == 1
        assert "GPU" in violations[0]

    def test_cost_violation(self) -> None:
        violations = self.engine.check_resource_limits(cpu=8, gpu=1, estimated_cost_usd=500.0)
        assert len(violations) == 1
        assert "cost" in violations[0].lower()

    def test_multiple_violations(self) -> None:
        violations = self.engine.check_resource_limits(cpu=256, gpu=16, estimated_cost_usd=500.0)
        assert len(violations) == 3

    def test_custom_limits(self) -> None:
        engine = PolicyEngine(
            config=PolicyConfig(max_cpu=4, max_gpu=0, max_estimated_cost_usd=10.0),
        )
        violations = engine.check_resource_limits(cpu=8, gpu=1, estimated_cost_usd=20.0)
        assert len(violations) == 3  # noqa: PLR2004
        assert any("CPU" in v for v in violations)
        assert any("GPU" in v for v in violations)
        assert any("cost" in v for v in violations)
