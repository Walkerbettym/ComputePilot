"""Policy engine for resource governance and approval gates."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyConfig(BaseModel):
    """Resource and approval policy configuration."""

    max_cpu: int = 128
    max_gpu: int = 8
    max_estimated_cost_usd: float = 100.0
    require_approval_if: list[str] = Field(
        default_factory=lambda: [
            "task_count > 1000",
            "command contains 'rm -rf'",
        ]
    )


class PolicyEngine:
    """Evaluates policy rules against a run or task request."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    def requires_approval(
        self,
        task_count: int = 0,
        total_cpu: int = 0,
        has_gpu: bool = False,
        command: str = "",
    ) -> bool:
        """Return True if the run requires human approval."""
        if task_count > self.config.max_cpu:
            return True
        if total_cpu > self.config.max_cpu:
            return True
        if has_gpu and self.config.max_gpu == 0:
            return True
        return "rm -rf" in command

    def check_resource_limits(
        self,
        cpu: int = 0,
        gpu: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> list[str]:
        """Return a list of limit violations (empty list = all clear)."""
        violations: list[str] = []
        if cpu > self.config.max_cpu:
            violations.append(f"CPU request ({cpu}) exceeds limit ({self.config.max_cpu})")
        if gpu > self.config.max_gpu:
            violations.append(f"GPU request ({gpu}) exceeds limit ({self.config.max_gpu})")
        if estimated_cost_usd > self.config.max_estimated_cost_usd:
            violations.append(
                f"Estimated cost (${estimated_cost_usd:.2f}) exceeds limit "
                f"(${self.config.max_estimated_cost_usd:.2f})"
            )
        return violations
