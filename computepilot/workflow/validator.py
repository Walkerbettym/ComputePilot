"""Workflow validation — structural, DAG, resource, I/O, and scientific checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from computepilot.models.workflow import TaskType, Workflow
from computepilot.workflow.dag import DAG


@dataclass
class ValidationError:
    """A single validation issue found during workflow validation."""

    code: str  # E-001, W-101, etc.
    message: str
    level: str  # "error" or "warning"
    location: str | None = None


@dataclass
class ValidationReport:
    """Aggregated result of a full workflow validation pass."""

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no error-level issues exist."""
        return not any(e.level == "error" for e in self.errors)


def validate(workflow: Workflow) -> ValidationReport:
    """Run all validation checks against *workflow*.

    Returns a :class:`ValidationReport` containing every error and warning
    discovered.
    """
    report = ValidationReport()
    _check_structural(workflow, report)
    _check_dag(workflow, report)
    _check_resources(workflow, report)
    _check_io(workflow, report)
    _check_scientific(workflow, report)
    return report


# ---------------------------------------------------------------------------
# Structural checks  (E-001 … E-009)
# ---------------------------------------------------------------------------


def _check_structural(workflow: Workflow, report: ValidationReport) -> None:
    ids = [t.id for t in workflow.tasks]
    task_ids = set(ids)

    # E-001 — duplicate task ids
    dupes = {tid for tid in ids if ids.count(tid) > 1}
    for d in dupes:
        report.errors.append(ValidationError("E-001", f"duplicate task id: {d}", "error"))

    # E-002 — depends_on references non-existent task
    for t in workflow.tasks:
        for dep in t.depends_on:
            if dep not in task_ids:
                report.errors.append(
                    ValidationError(
                        "E-002",
                        f"task '{t.id}' depends on unknown task '{dep}'",
                        "error",
                        t.id,
                    )
                )

    # E-004 — empty command
    for t in workflow.tasks:
        if not t.command.strip():
            report.errors.append(
                ValidationError("E-004", f"task '{t.id}' has empty command", "error", t.id)
            )

    # E-005 — task depends on itself
    for t in workflow.tasks:
        if t.id in t.depends_on:
            report.errors.append(
                ValidationError("E-005", f"task '{t.id}' depends on itself", "error", t.id)
            )

    # E-006 — invalid task type
    valid_types = set(TaskType)
    for t in workflow.tasks:
        if t.type not in valid_types:
            report.errors.append(
                ValidationError(
                    "E-006",
                    f"task '{t.id}' has invalid type '{t.type}'",
                    "error",
                    t.id,
                )
            )

    # E-007 — task has no command and no args (nothing to execute)
    for t in workflow.tasks:
        if not t.command.strip() and not t.args:
            report.errors.append(
                ValidationError(
                    "E-007", f"task '{t.id}' has no command and no arguments", "error", t.id
                )
            )

    # E-008 — task id exceeds 64 characters
    for t in workflow.tasks:
        if len(t.id) > 64:
            report.errors.append(
                ValidationError(
                    "E-008", f"task '{t.id}' id exceeds 64 character limit", "error", t.id
                )
            )

    # E-009 — workflow name does not match required pattern
    if not re.match(r"^[a-z0-9_-]{1,64}$", workflow.name):
        report.errors.append(
            ValidationError("E-009", f"workflow name '{workflow.name}' is invalid", "error")
        )


# ---------------------------------------------------------------------------
# DAG checks  (E-003)
# ---------------------------------------------------------------------------


def _check_dag(workflow: Workflow, report: ValidationReport) -> None:
    # E-003 — cycle in dependency graph
    try:
        dag = DAG(workflow)
        dag.topological_order()
    except ValueError:
        dag = DAG(workflow)
        cycle = dag.find_cycle()
        cycle_str = " -> ".join(cycle) if cycle else "unknown"
        report.errors.append(ValidationError("E-003", f"cycle detected: {cycle_str}", "error"))


# ---------------------------------------------------------------------------
# Resource checks  (E-100 … E-106)
# ---------------------------------------------------------------------------


def _check_resources(workflow: Workflow, report: ValidationReport) -> None:
    _memory_re = re.compile(r"^(\d+)\s*(MB|MiB|GB|GiB|TB|TiB)$")

    for t in workflow.tasks:
        res = t.resources

        # E-100 — cpu < 1
        if res.cpu < 1:
            report.errors.append(
                ValidationError("E-100", f"task '{t.id}' cpu={res.cpu} < 1", "error", t.id)
            )

        # E-101 — gpu < 0
        if res.gpu < 0:
            report.errors.append(
                ValidationError("E-101", f"task '{t.id}' gpu={res.gpu} < 0", "error", t.id)
            )

        # E-102 — memory format not parseable
        if not _memory_re.match(res.memory.strip()):
            report.errors.append(
                ValidationError(
                    "E-102", f"task '{t.id}' memory '{res.memory}' not parseable", "error", t.id
                )
            )

        # E-103 — empty partition name
        if res.partition is not None and not res.partition.strip():
            report.errors.append(
                ValidationError("E-103", f"task '{t.id}' has empty partition name", "error", t.id)
            )

        # E-104 — GPU requested with walltime > 7 days
        if res.gpu > 0 and res.walltime is not None and res.walltime.total_seconds() > 7 * 86400:
            report.errors.append(
                ValidationError(
                    "E-104",
                    f"task '{t.id}' gpu={res.gpu} with walltime > 7 days",
                    "error",
                    t.id,
                )
            )

        # E-105 — memory value exceeds reasonable limit
        mem_match = _memory_re.match(res.memory.strip())
        if mem_match:
            val, unit = int(mem_match.group(1)), mem_match.group(2)
            if unit in ("TB", "TiB") or (unit in ("GB", "GiB") and val > 1024):
                report.errors.append(
                    ValidationError(
                        "E-105",
                        f"task '{t.id}' memory '{res.memory}' exceeds limit",
                        "error",
                        t.id,
                    )
                )

        # E-106 — max_attempts out of range
        if t.retry_policy.max_attempts < 1 or t.retry_policy.max_attempts > 10:
            report.errors.append(
                ValidationError(
                    "E-106",
                    f"task '{t.id}' max_attempts={t.retry_policy.max_attempts} out of range [1,10]",
                    "error",
                    t.id,
                )
            )


# ---------------------------------------------------------------------------
# I/O checks  (E-200 … E-203)
# ---------------------------------------------------------------------------


def _check_io(workflow: Workflow, report: ValidationReport) -> None:
    task_ids = {t.id for t in workflow.tasks}

    outputs_map: dict[str, set[str]] = {}
    for t in workflow.tasks:
        outputs_map[t.id] = set(t.outputs)

    all_outputs: set[str] = set()
    for outs in outputs_map.values():
        all_outputs.update(outs)

    # E-200 — input references non-existent producer
    for t in workflow.tasks:
        for inp in t.inputs:
            if inp not in all_outputs:
                report.errors.append(
                    ValidationError(
                        "E-200",
                        f"task '{t.id}' input '{inp}' is not produced by any task",
                        "error",
                        t.id,
                    )
                )

    # E-201 — duplicate output names across tasks
    output_to_task: dict[str, str] = {}
    for t in workflow.tasks:
        for out in t.outputs:
            if out in output_to_task:
                report.errors.append(
                    ValidationError(
                        "E-201",
                        f"output '{out}' produced by both '{output_to_task[out]}' and '{t.id}'",
                        "error",
                        t.id,
                    )
                )
            else:
                output_to_task[out] = t.id

    # E-202 — task uses its own output as input
    for t in workflow.tasks:
        own_outputs = outputs_map.get(t.id, set())
        for inp in t.inputs:
            if inp in own_outputs:
                report.errors.append(
                    ValidationError(
                        "E-202",
                        f"task '{t.id}' consumes its own output '{inp}' as input",
                        "error",
                        t.id,
                    )
                )

    # E-203 — task depends on another task but consumes none of its outputs
    for t in workflow.tasks:
        if not t.inputs:
            continue
        for dep in t.depends_on:
            if dep in task_ids:
                dep_outputs = outputs_map.get(dep, set())
                if not any(inp in dep_outputs for inp in t.inputs):
                    report.errors.append(
                        ValidationError(
                            "E-203",
                            f"task '{t.id}' depends on '{dep}' but consumes no output from it",
                            "error",
                            t.id,
                        )
                    )


# ---------------------------------------------------------------------------
# Scientific checks  (W-101 … W-105)
# ---------------------------------------------------------------------------


def _check_scientific(workflow: Workflow, report: ValidationReport) -> None:
    for t in workflow.tasks:
        # W-101 — no random seed detected
        env_str = (
            " ".join(t.environment.keys())
            + " "
            + " ".join(t.environment.values())
            + " "
            + " ".join(t.args)
        )
        if "seed" not in env_str.lower() and "random" not in env_str.lower():
            report.errors.append(
                ValidationError("W-101", f"task '{t.id}': no random seed detected", "warning", t.id)
            )

        # W-102 — checkpointing disabled
        if not t.checkpoint:
            report.errors.append(
                ValidationError("W-102", f"task '{t.id}': checkpointing disabled", "warning", t.id)
            )

        # W-103 — no retry policy configured (max_attempts == 1)
        if t.retry_policy.max_attempts == 1:
            report.errors.append(
                ValidationError(
                    "W-103", f"task '{t.id}': no retry policy configured", "warning", t.id
                )
            )

        # W-104 — large resource allocation
        if t.resources.cpu > 64 or t.resources.gpu > 8:
            report.errors.append(
                ValidationError(
                    "W-104",
                    f"task '{t.id}': large resource allocation "
                    f"(cpu={t.resources.cpu}, gpu={t.resources.gpu})",
                    "warning",
                    t.id,
                )
            )

        # W-105 — no timeout set
        if t.timeout is None:
            report.errors.append(
                ValidationError("W-105", f"task '{t.id}': no timeout set", "warning", t.id)
            )
