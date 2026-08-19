"""Cost estimation for workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

from computepilot.models.workflow import TaskType, Workflow


@dataclass
class CostRow:
    """Cost estimate for a single task."""

    task_id: str
    task_type: TaskType
    estimated_cost: float
    unit: str = "USD"


@dataclass
class CostEstimate:
    """Full cost estimate for a workflow."""

    rows: list[CostRow] = field(default_factory=list)
    total_cost: float = 0.0
    currency: str = "USD"

    @property
    def task_count(self) -> int:
        return len(self.rows)


# Per-task-type cost per hour (placeholder values)
_DEFAULT_RATES: dict[TaskType, float] = {
    TaskType.PYTHON: 0.05,
    TaskType.SHELL: 0.03,
    TaskType.DOCKER: 0.10,
    TaskType.SLURM: 0.50,
}


class CostEstimator:
    """Estimate execution cost for a workflow."""

    def __init__(self, rates: dict[TaskType, float] | None = None) -> None:
        self._rates = {**_DEFAULT_RATES, **(rates or {})}

    def estimate(self, workflow: Workflow) -> CostEstimate:
        """Estimate the cost of running a workflow."""
        rows: list[CostRow] = []
        total = 0.0

        for task in workflow.tasks:
            rate = self._rates.get(task.type, 0.05)
            # Assume 1 hour per task as default
            cost = rate
            rows.append(
                CostRow(
                    task_id=task.id,
                    task_type=task.type,
                    estimated_cost=cost,
                )
            )
            total += cost

        return CostEstimate(rows=rows, total_cost=total, currency="USD")
