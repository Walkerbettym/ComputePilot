import pytest
from pydantic import ValidationError

from sciflow.models.workflow import Resources, Task, TaskType, Workflow


def test_task_minimal() -> None:
    t = Task(id="hello", command="echo hello")
    assert t.id == "hello"
    assert t.type == TaskType.PYTHON


def test_task_invalid_id() -> None:
    with pytest.raises(ValidationError, match="id"):
        Task(id="123-bad", command="echo")


def test_resources_cpu_negative() -> None:
    with pytest.raises(ValidationError, match="cpu"):
        Resources(cpu=0)


def test_resources_memory_parseable() -> None:
    r = Resources(memory="4GiB")
    assert r.memory == "4GiB"
    with pytest.raises(ValidationError, match="memory"):
        Resources(memory="not-a-size")


def test_workflow_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Workflow(
            name="test",
            tasks=[
                Task(id="a", command="cmd1"),
                Task(id="a", command="cmd2"),
            ],
        )


def test_workflow_empty_tasks() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        Workflow(name="test", tasks=[])
