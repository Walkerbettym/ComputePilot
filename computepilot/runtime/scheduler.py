"""Task scheduler with concurrency control."""

from __future__ import annotations

from computepilot.models.workflow import Task, Workflow
from computepilot.workflow.dag import DAG


class Scheduler:
    """Drives task execution in dependency order with a concurrency limit.

    Usage::

        dag = build_dag(workflow)
        sched = Scheduler(dag, max_concurrency=4)
        while sched.has_pending():
            for task in sched.ready():
                # submit task
                ...
            sched.done(task_id)
    """

    def __init__(self, workflow_or_dag: Workflow | DAG, max_concurrency: int = 4) -> None:
        if isinstance(workflow_or_dag, DAG):
            self._dag = workflow_or_dag
        else:
            from computepilot.workflow.dag import build_dag

            self._dag = build_dag(workflow_or_dag)
        self._max_concurrency = max_concurrency
        self._completed: set[str] = set()
        self._in_flight: set[str] = set()

    # -- Public API ------------------------------------------------------------

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @max_concurrency.setter
    def max_concurrency(self, value: int) -> None:
        self._max_concurrency = value

    def has_pending(self) -> bool:
        """Return ``True`` if there are tasks not yet completed."""
        return len(self._completed) < len(self._dag.topological_order())

    def ready(self) -> list[Task]:
        """Return tasks that are ready to run (deps satisfied + concurrency slot open).

        When slots are contended, higher ``priority`` wins; ties break by
        topological order (stable).
        """
        slot_count = self._max_concurrency - len(self._in_flight)
        if slot_count <= 0:
            return []
        candidates = self._dag.ready_tasks(self._completed)
        # Exclude tasks already in-flight
        candidates = [t for t in candidates if t.id not in self._in_flight]
        topo_index = {tid: i for i, tid in enumerate(self._dag.topological_order())}
        candidates.sort(key=lambda t: (-t.priority, topo_index.get(t.id, 0)))
        ready = candidates[:slot_count]
        for t in ready:
            self._in_flight.add(t.id)
        return ready

    def done(self, task_id: str) -> None:
        """Mark *task_id* as finished so downstream tasks may become ready."""
        self._completed.add(task_id)
        self._in_flight.discard(task_id)

    def release(self, task_id: str) -> None:
        """Release *task_id* from in-flight without marking it completed.

        This allows a failed task to be re-queued for retry.
        """
        self._in_flight.discard(task_id)

    def completed(self) -> set[str]:
        """Return the set of completed task ids."""
        return self._completed.copy()

    def in_flight(self) -> set[str]:
        """Return the set of currently running task ids."""
        return self._in_flight.copy()
