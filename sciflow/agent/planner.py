"""Planner — converts Intent into a Workflow definition."""

from __future__ import annotations

from sciflow.agent.intent import Intent
from sciflow.models.workflow import Resources, Task, TaskType, Workflow


class Planner:
    """Build a Workflow from a structured Intent."""

    def plan(self, intent: Intent) -> Workflow:
        """Convert an Intent into a Workflow definition."""
        tasks = self._build_tasks(intent)
        return Workflow(
            name=f"{intent.verb}_{intent.target}".replace(" ", "_").replace(".", "_").lower()[:64],
            description=f"{intent.verb} {intent.target}",
            tasks=tasks,
        )

    def _build_tasks(self, intent: Intent) -> list[Task]:
        """Build a list of Task objects from the Intent."""
        tasks: list[Task] = []

        # Default resources from intent
        res = Resources(
            cpu=int(intent.resources.get("cpu", 1)),
            memory=str(intent.resources.get("memory", "2GB")),
            gpu=int(intent.resources.get("gpu", 0)),
        )

        # Determine task type based on verb
        task_type = self._infer_task_type(intent.verb)

        # Build the primary task
        command = self._build_command(intent)
        id_slug = (
            f"{intent.verb}_{intent.target}".replace(" ", "_")
            .replace("-", "_")
            .replace(".", "_")
            .lower()[:64]
        )
        task = Task(
            id=id_slug,
            type=task_type,
            command=command,
            resources=res,
            environment=dict(intent.parameters.get("env", {})),
        )
        tasks.append(task)

        # Add a preprocess step if the intent mentions data preparation
        if any(kw in intent.verb.lower() for kw in ("preprocess", "prepare", "clean")):
            tasks.insert(
                0,
                Task(
                    id="preprocess_data",
                    type=TaskType.PYTHON,
                    command=intent.parameters.get("preprocess_command", "python preprocess.py"),
                    resources=res,
                ),
            )
            task.depends_on = ["preprocess_data"]

        return tasks[:50]  # cap at 50 tasks

    @staticmethod
    def _infer_task_type(verb: str) -> TaskType:
        """Infer the task type from the verb."""
        verb_lower = verb.lower()
        if verb_lower in ("shell", "bash", "script"):
            return TaskType.SHELL
        if verb_lower in ("container", "docker"):
            return TaskType.DOCKER
        if verb_lower in ("slurm", "sbatch"):
            return TaskType.SLURM
        return TaskType.PYTHON

    @staticmethod
    def _build_command(intent: Intent) -> str:
        """Build a command string from the Intent."""
        params = intent.parameters
        if "command" in params:
            return str(params["command"])
        if "script" in params:
            return str(params["script"])
        if "entry_point" in params:
            return str(params["entry_point"])
        return f"python run.py --task {intent.verb} --target {intent.target}"
