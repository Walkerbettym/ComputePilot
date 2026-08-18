"""Tests for the workflow validator — covers all 24 error codes."""

from __future__ import annotations

from datetime import timedelta

from sciflow.models.workflow import Resources, RetryPolicy, Task, Workflow
from sciflow.workflow.validator import ValidationError, ValidationReport, validate


def _make_workflow(name: str = "test", tasks: list[Task] | None = None) -> Workflow:
    """Helper: create a valid base workflow."""
    return Workflow(name=name, tasks=tasks or [Task(id="a", command="echo hello")])


# ---------------------------------------------------------------------------
# E-001: duplicate task ids
# ---------------------------------------------------------------------------


def test_e001_duplicate_task_ids() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(id="a", command="cmd"),
            Task.model_construct(id="a", command="cmd2"),
        ],
    )
    report = validate(wf)
    assert not report.passed
    codes = [e.code for e in report.errors]
    assert "E-001" in codes


# ---------------------------------------------------------------------------
# E-002: depends_on references non-existent
# ---------------------------------------------------------------------------


def test_e002_unknown_dependency() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd", depends_on=["nonexistent"])])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-002" for e in report.errors)


# ---------------------------------------------------------------------------
# E-003: cycle in DAG
# ---------------------------------------------------------------------------


def test_e003_cycle() -> None:
    wf = _make_workflow(
        tasks=[
            Task(id="a", command="cmd", depends_on=["c"]),
            Task(id="b", command="cmd", depends_on=["a"]),
            Task(id="c", command="cmd", depends_on=["b"]),
        ]
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-003" for e in report.errors)


# ---------------------------------------------------------------------------
# E-004: empty command
# ---------------------------------------------------------------------------


def test_e004_empty_command() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="")])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-004" for e in report.errors)


# ---------------------------------------------------------------------------
# E-005: self-referencing dependency
# ---------------------------------------------------------------------------


def test_e005_self_dependency() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd", depends_on=["a"])])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-005" for e in report.errors)


# ---------------------------------------------------------------------------
# E-006: invalid task type
# ---------------------------------------------------------------------------


def test_e006_invalid_task_type() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[Task.model_construct(id="a", command="cmd", type="invalid_type")],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-006" for e in report.errors)


# ---------------------------------------------------------------------------
# E-007: no command and no args
# ---------------------------------------------------------------------------


def test_e007_no_command_no_args() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="", args=[])])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-007" for e in report.errors)


# ---------------------------------------------------------------------------
# E-008: task id too long
# ---------------------------------------------------------------------------


def test_e008_task_id_too_long() -> None:
    long_id = "a" + "x" * 64  # 65 chars
    wf = _make_workflow(tasks=[Task(id=long_id, command="cmd")])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-008" for e in report.errors)


# ---------------------------------------------------------------------------
# E-009: workflow name invalid
# ---------------------------------------------------------------------------


def test_e009_invalid_workflow_name() -> None:
    wf = Workflow.model_construct(
        name="UPPERCASE",
        tasks=[Task.model_construct(id="a", command="cmd")],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-009" for e in report.errors)


# ---------------------------------------------------------------------------
# E-100: cpu < 1
# ---------------------------------------------------------------------------


def test_e100_cpu_less_than_one() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(cpu=0),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-100" for e in report.errors)


# ---------------------------------------------------------------------------
# E-101: gpu < 0
# ---------------------------------------------------------------------------


def test_e101_gpu_negative() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(gpu=-1),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-101" for e in report.errors)


# ---------------------------------------------------------------------------
# E-102: memory format not parseable
# ---------------------------------------------------------------------------


def test_e102_invalid_memory_format() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(memory="invalid"),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-102" for e in report.errors)


# ---------------------------------------------------------------------------
# E-103: empty partition name
# ---------------------------------------------------------------------------


def test_e103_empty_partition() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(partition=""),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-103" for e in report.errors)


# ---------------------------------------------------------------------------
# E-104: GPU with walltime > 7 days
# ---------------------------------------------------------------------------


def test_e104_gpu_long_walltime() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(
                    gpu=1, walltime=timedelta(days=8)
                ),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-104" for e in report.errors)


# ---------------------------------------------------------------------------
# E-105: memory exceeds limit
# ---------------------------------------------------------------------------


def test_e105_memory_exceeds_limit() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                resources=Resources.model_construct(memory="2048GB"),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-105" for e in report.errors)


# ---------------------------------------------------------------------------
# E-106: max_attempts out of range
# ---------------------------------------------------------------------------


def test_e106_max_attempts_out_of_range() -> None:
    wf = Workflow.model_construct(
        name="test",
        tasks=[
            Task.model_construct(
                id="a",
                command="cmd",
                retry_policy=RetryPolicy.model_construct(max_attempts=0),
            )
        ],
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-106" for e in report.errors)


# ---------------------------------------------------------------------------
# E-200: input references non-existent producer
# ---------------------------------------------------------------------------


def test_e200_input_not_produced() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd", inputs=["nonexistent"])])
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-200" for e in report.errors)


# ---------------------------------------------------------------------------
# E-201: duplicate output names
# ---------------------------------------------------------------------------


def test_e201_duplicate_outputs() -> None:
    wf = _make_workflow(
        tasks=[
            Task(id="a", command="cmd", outputs=["result.txt"]),
            Task(id="b", command="cmd2", outputs=["result.txt"]),
        ]
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-201" for e in report.errors)


# ---------------------------------------------------------------------------
# E-202: task uses own output as input
# ---------------------------------------------------------------------------


def test_e202_self_input() -> None:
    wf = _make_workflow(
        tasks=[Task(id="a", command="cmd", outputs=["out.txt"], inputs=["out.txt"])]
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-202" for e in report.errors)


# ---------------------------------------------------------------------------
# E-203: depends on task but consumes no output from it
# ---------------------------------------------------------------------------


def test_e203_depends_but_no_output_consumed() -> None:
    wf = _make_workflow(
        tasks=[
            Task(id="a", command="cmd", outputs=["data.txt"]),
            Task(id="b", command="cmd2", depends_on=["a"], inputs=["other.txt"]),
        ]
    )
    report = validate(wf)
    assert not report.passed
    assert any(e.code == "E-203" for e in report.errors)


# ---------------------------------------------------------------------------
# W-101: no random seed detected
# ---------------------------------------------------------------------------


def test_w101_no_random_seed() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="echo hello")])
    report = validate(wf)
    assert report.passed  # warnings don't fail
    assert any(e.code == "W-101" for e in report.errors)


def test_w101_suppressed_by_seed_env() -> None:
    wf = _make_workflow(
        tasks=[Task(id="a", command="python run.py", environment={"SEED": "42"})]
    )
    report = validate(wf)
    assert not any(e.code == "W-101" for e in report.errors)


def test_w101_suppressed_by_random_arg() -> None:
    wf = _make_workflow(
        tasks=[Task(id="a", command="python run.py", args=["--random-state", "42"])]
    )
    report = validate(wf)
    assert not any(e.code == "W-101" for e in report.errors)


# ---------------------------------------------------------------------------
# W-102: checkpointing disabled
# ---------------------------------------------------------------------------


def test_w102_no_checkpoint() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd", checkpoint=False)])
    report = validate(wf)
    assert report.passed
    assert any(e.code == "W-102" for e in report.errors)


# ---------------------------------------------------------------------------
# W-103: no retry policy configured
# ---------------------------------------------------------------------------


def test_w103_no_retry() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd")])
    report = validate(wf)
    assert report.passed
    assert any(e.code == "W-103" for e in report.errors)


def test_w103_suppressed_by_retry() -> None:
    wf = _make_workflow(
        tasks=[
            Task(
                id="a",
                command="cmd",
                retry_policy=RetryPolicy(max_attempts=3),
            )
        ]
    )
    report = validate(wf)
    assert not any(e.code == "W-103" for e in report.errors)


# ---------------------------------------------------------------------------
# W-104: large resource allocation
# ---------------------------------------------------------------------------


def test_w104_large_cpu() -> None:
    wf = _make_workflow(
        tasks=[
            Task(id="a", command="cmd", resources=Resources(cpu=128, memory="4GB"))
        ]
    )
    report = validate(wf)
    assert report.passed
    assert any(e.code == "W-104" for e in report.errors)


def test_w104_large_gpu() -> None:
    wf = _make_workflow(
        tasks=[
            Task(
                id="a", command="cmd", resources=Resources(cpu=4, gpu=16, memory="4GB")
            )
        ]
    )
    report = validate(wf)
    assert report.passed
    assert any(e.code == "W-104" for e in report.errors)


# ---------------------------------------------------------------------------
# W-105: no timeout set
# ---------------------------------------------------------------------------


def test_w105_no_timeout() -> None:
    wf = _make_workflow(tasks=[Task(id="a", command="cmd")])
    report = validate(wf)
    assert report.passed
    assert any(e.code == "W-105" for e in report.errors)


def test_w105_suppressed_by_timeout() -> None:
    wf = _make_workflow(
        tasks=[Task(id="a", command="cmd", timeout=timedelta(hours=1))]
    )
    report = validate(wf)
    assert not any(e.code == "W-105" for e in report.errors)


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


def test_validation_report_passed() -> None:
    report = ValidationReport()
    report.errors.append(ValidationError("W-101", "warn", "warning"))
    assert report.passed

    report.errors.append(ValidationError("E-001", "error", "error"))
    assert not report.passed


def test_valid_workflow_passes() -> None:
    wf = _make_workflow()
    report = validate(wf)
    assert report.passed


def test_valid_workflow_with_seed_passes() -> None:
    wf = _make_workflow(
        tasks=[Task(id="a", command="python train.py", args=["--seed", "42"])]
    )
    report = validate(wf)
    assert report.passed


def test_valid_workflow_with_retry_passes() -> None:
    wf = _make_workflow(
        tasks=[
            Task(
                id="a",
                command="cmd",
                retry_policy=RetryPolicy(max_attempts=3, backoff="fixed"),
                timeout=timedelta(hours=2),
            )
        ]
    )
    report = validate(wf)
    assert report.passed
