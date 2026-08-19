"""DAG (Directed Acyclic Graph) for workflow task scheduling."""

from collections import defaultdict

from computepilot.models.workflow import Task, Workflow


def build_dag(workflow: Workflow) -> "DAG":
    """Convenience factory — create a DAG from a Workflow."""
    return DAG(workflow)


class DAG:
    """Represents the dependency graph of a workflow's tasks."""

    def __init__(self, workflow: Workflow) -> None:
        self.workflow = workflow
        self._adj: dict[str, list[str]] = defaultdict(list)  # task_id → downstream
        self._in_degree: dict[str, int] = defaultdict(int)
        self._task_map: dict[str, Task] = {t.id: t for t in workflow.tasks}
        self._build()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build(self) -> None:
        for t in self.workflow.tasks:
            for dep in t.depends_on:
                self._adj[dep].append(t.id)
                self._in_degree[t.id] += 1
            if t.id not in self._in_degree:
                self._in_degree[t.id] = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def topological_order(self) -> list[str]:
        """Kahn's algorithm; returns task IDs in topological order.

        Raises ``ValueError`` if a cycle is present.
        """
        in_deg = dict(self._in_degree)
        queue = [tid for tid, d in in_deg.items() if d == 0]
        result: list[str] = []
        while queue:
            tid = queue.pop(0)
            result.append(tid)
            for downstream in self._adj[tid]:
                in_deg[downstream] -= 1
                if in_deg[downstream] == 0:
                    queue.append(downstream)
        if len(result) != len(self._in_degree):
            raise ValueError("cycle detected in DAG")
        return result

    def find_cycle(self) -> list[str]:
        """Return a cycle path if one exists, otherwise an empty list."""
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            visited.add(node)
            path.append(node)
            for neighbor in self._adj[node]:
                if neighbor in path:
                    return path[path.index(neighbor) :] + [neighbor]
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
            path.pop()
            return None

        for tid in self._in_degree:
            if tid not in visited:
                result = dfs(tid)
                if result:
                    return result
        return []

    def ready_tasks(self, completed: set[str]) -> list[Task]:
        """Return tasks whose dependencies are all *completed*."""
        in_deg = dict(self._in_degree)
        for tid in completed:
            for downstream in self._adj[tid]:
                in_deg[downstream] -= 1
        ready = [
            self._task_map[tid] for tid, d in in_deg.items() if d <= 0 and tid not in completed
        ]
        return ready
