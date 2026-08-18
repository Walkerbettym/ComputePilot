"""Workflow execution engine — orchestrates a single run."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sciflow.models.run import Run, RunStatus, TaskStatus
from sciflow.models.workflow import Workflow
from sciflow.runtime.executor import Executor
from sciflow.runtime.scheduler import Scheduler
from sciflow.runtime.state import StateStore
from sciflow.workflow.dag import build_dag

DEFAULT_POLL_INTERVAL = 0.25


class Engine:
    """Orchestrates a single workflow run.

    Typical usage::

        engine = Engine(state=store, executor=local_executor)
        run = await engine.run(workflow, config={...})
    """

    def __init__(
        self,
        state: StateStore,
        executor: Executor,
        max_concurrency: int = 4,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._state = state
        self._executor = executor
        self._max_concurrency = max_concurrency
        self._poll_interval = poll_interval

    # -- Public API ------------------------------------------------------------

    async def run(
        self,
        workflow: Workflow,
        run_id: str,
        config: dict[str, Any] | None = None,
        run_dir: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Run:
        """Execute *workflow* and return the final ``Run`` object."""
        _run_dir = Path(run_dir) if run_dir else Path.cwd() / "runs" / run_id
        _run_dir.mkdir(parents=True, exist_ok=True)

        run = Run(
            id=run_id,
            workflow_id=workflow.id,
            workflow_sha256=workflow.sha256,
            status=RunStatus.RUNNING,
            executor=self._executor.name,
            config=config or {},
            created_at=datetime.now(tz=UTC),
            started_at=datetime.now(tz=UTC),
            run_dir=_run_dir,
        )
        self._state.create_run(run)

        dag = build_dag(workflow)
        sched = Scheduler(dag, self._max_concurrency)

        # Validate all tasks before starting
        for task in workflow.tasks:
            errors = self._executor.validate_task(task)
            if errors:
                run.status = RunStatus.FAILED
                run.finished_at = datetime.now(tz=UTC)
                self._state.update_run_status(run.id, RunStatus.FAILED)
                return run

        handles: dict[str, Any] = {}
        running_tasks: dict[str, asyncio.Task[Any]] = {}

        try:
            while sched.has_pending():
                ready_tasks = sched.ready()
                for task in ready_tasks:
                    self._state.transition_task(
                        run.id, task.id, TaskStatus.RUNNING, attempt=0
                    )
                    env_full = {**workflow.env, **task.environment, **(env or {})}
                    handle = await self._executor.submit(task, str(_run_dir), env_full)
                    handles[task.id] = handle
                    running_tasks[task.id] = asyncio.create_task(
                        self._poll_and_collect(task.id, handle)
                    )

                if running_tasks:
                    done_set, _ = await asyncio.wait(
                        running_tasks.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=self._poll_interval,
                    )
                    for done_task in done_set:
                        task_id, result = done_task.result()
                        del running_tasks[task_id]
                        ok = result.ok
                        final_status = (
                            TaskStatus.SUCCEEDED if ok else TaskStatus.FAILED
                        )
                        self._state.transition_task(
                            run.id,
                            task_id,
                            final_status,
                            attempt=0,
                            exit_code=result.exit_code,
                            error=result.error,
                        )
                        sched.done(task_id)
                else:
                    # No tasks in flight and nothing ready — wait then re-check
                    await asyncio.sleep(self._poll_interval)

            run.status = RunStatus.SUCCEEDED
        except (Exception, asyncio.CancelledError) as exc:
            run.status = RunStatus.FAILED
            # Cancel any in-flight tasks
            for running_task in running_tasks.values():
                running_task.cancel()
            if running_tasks:
                await asyncio.gather(*running_tasks.values(), return_exceptions=True)
            # Mark remaining in-flight as failed in state
            for tid in list(running_tasks.keys()):
                self._state.transition_task(
                    run.id, tid, TaskStatus.FAILED, error=str(exc)
                )
                sched.done(tid)

        run.finished_at = datetime.now(tz=UTC)
        self._state.update_run_status(run.id, run.status)
        return run

    # -- Internal helpers ------------------------------------------------------

    async def _poll_and_collect(
        self, task_id: str, handle: Any
    ) -> tuple[str, Any]:
        """Poll the executor until the task finishes, then collect the result."""
        while True:
            status = await self._executor.status(handle)
            if status in (
                TaskStatus.SUCCEEDED, TaskStatus.FAILED,
                TaskStatus.SKIPPED, TaskStatus.CANCELLED,
            ):
                result = await self._executor.collect(handle)
                return task_id, result
            await asyncio.sleep(self._poll_interval)
