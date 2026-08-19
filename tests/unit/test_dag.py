"""Tests for the DAG class."""

import pytest

from computepilot.models.workflow import Task, Workflow
from computepilot.workflow.dag import DAG, build_dag


class TestTopologicalOrder:
    """Tests for DAG.topological_order()."""

    def test_linear_chain(self) -> None:
        wf = Workflow(
            name="linear",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["b"]),
            ],
        )
        dag = DAG(wf)
        assert dag.topological_order() == ["a", "b", "c"]

    def test_parallel_fan_out(self) -> None:
        wf = Workflow(
            name="parallel",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["a"]),
                Task(id="d", command="cmd", depends_on=["a"]),
            ],
        )
        dag = DAG(wf)
        order = dag.topological_order()
        assert order[0] == "a"
        assert set(order[1:]) == {"b", "c", "d"}

    def test_no_dependencies(self) -> None:
        wf = Workflow(
            name="independent",
            tasks=[
                Task(id="x", command="cmd"),
                Task(id="y", command="cmd"),
                Task(id="z", command="cmd"),
            ],
        )
        dag = DAG(wf)
        order = dag.topological_order()
        assert set(order) == {"x", "y", "z"}

    def test_diamond_shape(self) -> None:
        wf = Workflow(
            name="diamond",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["a"]),
                Task(id="d", command="cmd", depends_on=["b", "c"]),
            ],
        )
        dag = DAG(wf)
        order = dag.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_build_dag_factory(self) -> None:
        wf = Workflow(
            name="factory",
            tasks=[Task(id="a", command="cmd")],
        )
        dag = build_dag(wf)
        assert isinstance(dag, DAG)
        assert dag.topological_order() == ["a"]


class TestCycleDetection:
    """Tests for DAG.find_cycle()."""

    def test_three_node_cycle(self) -> None:
        wf = Workflow(
            name="cycle3",
            tasks=[
                Task(id="a", command="cmd", depends_on=["c"]),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["b"]),
            ],
        )
        dag = DAG(wf)
        cycle = dag.find_cycle()
        assert len(cycle) >= 3
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_order()

    def test_self_loop(self) -> None:
        wf = Workflow(
            name="self-loop",
            tasks=[
                Task(id="a", command="cmd", depends_on=["a"]),
            ],
        )
        dag = DAG(wf)
        cycle = dag.find_cycle()
        assert len(cycle) >= 2

    def test_acyclic_returns_empty(self) -> None:
        wf = Workflow(
            name="no-cycle",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
            ],
        )
        dag = DAG(wf)
        assert dag.find_cycle() == []


class TestReadyTasks:
    """Tests for DAG.ready_tasks()."""

    def test_initial_root_task(self) -> None:
        wf = Workflow(
            name="ready",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["a"]),
            ],
        )
        dag = DAG(wf)
        ready = dag.ready_tasks(set())
        assert [t.id for t in ready] == ["a"]

    def test_after_completing_root(self) -> None:
        wf = Workflow(
            name="ready2",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["a"]),
            ],
        )
        dag = DAG(wf)
        ready = dag.ready_tasks({"a"})
        assert set(t.id for t in ready) == {"b", "c"}

    def test_completed_task_excluded_from_ready(self) -> None:
        wf = Workflow(
            name="exclude-completed",
            tasks=[
                Task(id="a", command="cmd"),
            ],
        )
        dag = DAG(wf)
        assert dag.ready_tasks({"a"}) == []

    def test_multi_level_ready(self) -> None:
        wf = Workflow(
            name="multi-level",
            tasks=[
                Task(id="a", command="cmd"),
                Task(id="b", command="cmd", depends_on=["a"]),
                Task(id="c", command="cmd", depends_on=["b"]),
            ],
        )
        dag = DAG(wf)
        assert [t.id for t in dag.ready_tasks({"a", "b"})] == ["c"]
