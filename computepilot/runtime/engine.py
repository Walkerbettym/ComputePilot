"""Workflow execution engine — orchestrates a single run."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.models.workflow import Task, Workflow
from computepilot.policy.engine import PolicyEngine
from computepilot.runtime.executor import (
    DiagnosisHandler,
    DiagnosisResult,
    Executor,
    RepairSpec,
    TaskResult,
)
from computepilot.runtime.retry import next_delay, should_retry
from computepilot.runtime.scheduler import Scheduler
from computepilot.runtime.state import StateStore
from computepilot.workflow.dag import build_dag

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
        diagnosis_handler: DiagnosisHandler | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self._state = state
        self._executor = executor
        self._max_concurrency = max_concurrency
        self._poll_interval = poll_interval
        self._diagnosis_handler = diagnosis_handler
        self._policy_engine = policy_engine or PolicyEngine()
        self._attempts: dict[str, int] = {}

    # -- Public API ------------------------------------------------------------

    async def run(
        self,
        workflow: Workflow,
        run_id: str,
        config: dict[str, Any] | None = None,
        run_dir: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Run:
        _run_dir = Path(run_dir) if run_dir else Path.cwd() / "runs" / run_id
        _run_dir.mkdir(parents=True, exist_ok=True)
        run = Run(
            id=run_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
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
        human_intervention = False

        try:
            while sched.has_pending() and not human_intervention:
                ready_tasks = sched.ready()
                for task in ready_tasks:
                    attempt = self._attempts.get(task.id, 0)
                    self._state.transition_task(
                        run.id,
                        task.id,
                        TaskStatus.RUNNING,
                        attempt=attempt,
                    )
                    env_full = {**workflow.env, **task.environment, **(env or {})}
                    handle = await self._executor.submit(task, str(_run_dir), env_full)
                    handles[task.id] = handle
                    running_tasks[task.id] = asyncio.create_task(
                        self._poll_and_collect(task.id, handle, task)
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
                        task_obj = self._get_task(workflow, task_id)
                        if ok:
                            final_status = TaskStatus.SUCCEEDED
                            self._state.transition_task(
                                run.id,
                                task_id,
                                final_status,
                                attempt=self._attempts.get(task_id, 0),
                                exit_code=result.exit_code,
                                error=result.error,
                            )
                            sched.done(task_id)
                        else:
                            human_intervention = await self._handle_failure(
                                run,
                                task_obj,
                                task_id,
                                result,
                                sched,
                            )
                else:
                    # No tasks in flight, nothing ready, but pending exist — deadlock.
                    # This can happen with max_concurrency=0 or unresolvable dependencies.
                    run.status = RunStatus.FAILED
                    for tid, _task in [(t.id, t) for t in workflow.tasks]:
                        state = self._state.get_task_state(run.id, tid)
                        if state is None or state in (TaskStatus.PENDING, TaskStatus.READY):
                            self._state.transition_task(
                                run.id,
                                tid,
                                TaskStatus.SKIPPED,
                                error="deadlock: no ready tasks available",
                            )
                    break

            if human_intervention:
                run.status = RunStatus.FAILED
            else:
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
                self._state.transition_task(run.id, tid, TaskStatus.FAILED, error=str(exc))
                sched.done(tid)

        run.finished_at = datetime.now(tz=UTC)
        self._state.update_run_status(run.id, run.status)

        return run

    async def resume(
        self,
        workflow: Workflow,
        run_id: str,
        run_dir: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Run:
        """Resume a previously-started run, skipping completed tasks.

        The *workflow* must be the same workflow that was used for the
        original run.  Completed tasks are loaded from the state store;
        only unfinished tasks are executed.
        """
        run_data = self._state.get_run(run_id)
        if run_data is None:
            msg = f"run '{run_id}' not found"
            raise ValueError(msg)

        run = Run(
            id=run_data["id"],
            workflow_id=run_data["workflow_id"],
            workflow_name=run_data.get("workflow_name", ""),
            workflow_sha256=run_data["workflow_sha256"],
            status=RunStatus.RESUMING,
            executor=run_data["executor"],
            config=json.loads(run_data["config_json"]),
            created_at=datetime.fromisoformat(run_data["created_at"]),
        )
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(tz=UTC)
        self._state.update_run_status(run.id, RunStatus.RUNNING)

        _run_dir = Path(run_dir) if run_dir else Path.cwd()
        _run_dir.mkdir(parents=True, exist_ok=True)

        dag = build_dag(workflow)
        sched = Scheduler(dag, self._max_concurrency)

        # Mark already-completed tasks so the scheduler skips them
        completed = self._state.get_completed_tasks(run_id)
        for tid in completed:
            sched.done(tid)

        handles: dict[str, Any] = {}
        running_tasks: dict[str, asyncio.Task[Any]] = {}
        human_intervention = False

        try:
            while sched.has_pending() and not human_intervention:
                ready_tasks = sched.ready()
                for task in ready_tasks:
                    attempt = self._attempts.get(task.id, 0)
                    self._state.transition_task(
                        run.id,
                        task.id,
                        TaskStatus.RUNNING,
                        attempt=attempt,
                    )
                    env_full = {**workflow.env, **task.environment, **(env or {})}
                    handle = await self._executor.submit(
                        task,
                        str(_run_dir),
                        env_full,
                    )
                    handles[task.id] = handle
                    running_tasks[task.id] = asyncio.create_task(
                        self._poll_and_collect(task.id, handle, task)
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
                        task_obj = self._get_task(workflow, task_id)
                        if result.ok:
                            self._state.transition_task(
                                run.id,
                                task_id,
                                TaskStatus.SUCCEEDED,
                                attempt=self._attempts.get(task_id, 0),
                                exit_code=result.exit_code,
                                error=result.error,
                            )
                            sched.done(task_id)
                        else:
                            human_intervention = await self._handle_failure(
                                run,
                                task_obj,
                                task_id,
                                result,
                                sched,
                            )
                else:
                    # No tasks in flight, nothing ready — deadlock
                    run.status = RunStatus.FAILED
                    for tid in list(running_tasks.keys()):
                        self._state.transition_task(
                            run.id,
                            tid,
                            TaskStatus.SKIPPED,
                            error="deadlock: no ready tasks available",
                        )
                    break

            if human_intervention:
                run.status = RunStatus.FAILED
            else:
                run.status = RunStatus.SUCCEEDED
        except (Exception, asyncio.CancelledError) as exc:
            run.status = RunStatus.FAILED
            for running_task in running_tasks.values():
                running_task.cancel()
            if running_tasks:
                await asyncio.gather(*running_tasks.values(), return_exceptions=True)
            for tid in list(running_tasks.keys()):
                self._state.transition_task(run.id, tid, TaskStatus.FAILED, error=str(exc))
                sched.done(tid)

        run.finished_at = datetime.now(tz=UTC)
        self._state.update_run_status(run.id, run.status)
        return run

    # -- Internal helpers ------------------------------------------------------

    async def _poll_and_collect(
        self, task_id: str, handle: Any, task: Task | None = None
    ) -> tuple[str, Any]:
        """Poll the executor until the task finishes, then collect the result.

        A watch dog ensures tasks that exceed *task.timeout* are cancelled
        and reported as FAILED.
        """
        deadline: datetime | None = None
        if task is not None and task.timeout is not None:
            deadline = datetime.now(tz=UTC) + task.timeout
        else:
            # Default timeout: 1 hour per task
            deadline = datetime.now(tz=UTC) + timedelta(hours=1)

        while True:
            if datetime.now(tz=UTC) > deadline:
                await self._executor.cancel(handle)
                # Wait a moment for cancellation to take effect
                await asyncio.sleep(0.5)
                return task_id, TaskResult(
                    task_id=task_id,
                    ok=False,
                    exit_code=None,
                    error="task timed out and was cancelled",
                )

            status = await self._executor.status(handle)
            if status in (
                TaskStatus.SUCCEEDED,
                TaskStatus.FAILED,
                TaskStatus.SKIPPED,
                TaskStatus.CANCELLED,
            ):
                result = await self._executor.collect(handle)
                return task_id, result
            await asyncio.sleep(self._poll_interval)

    async def _handle_failure(
        self,
        run: Run,
        task: Task,
        task_id: str,
        result: Any,
        sched: Scheduler,
    ) -> bool:
        """Handle a failed task. Returns True if human intervention stops the run."""
        self._attempts.setdefault(task_id, 0)
        attempt = self._attempts[task_id]

        # Always diagnose the failure
        if self._diagnosis_handler is not None:
            diagnosis = self._diagnosis_handler.diagnose(
                task_id,
                exit_code=result.exit_code,
                stderr=result.stderr_tail or result.error or "",
            )
        else:
            diagnosis = DiagnosisResult(
                task_id=task_id,
                cause="UNKNOWN",
                suggested_action="human",
                explanation="no diagnosis handler configured",
            )

        # Record diagnosis event
        self._state.record_event(
            run.id,
            task_id,
            "diagnosis",
            payload={
                "cause": diagnosis.cause,
                "confidence": diagnosis.confidence,
                "explanation": diagnosis.explanation,
                "suggested_action": diagnosis.suggested_action,
                "repair": {
                    "action": diagnosis.repair.action,
                    "params": diagnosis.repair.params,
                }
                if diagnosis.repair
                else None,
            },
        )

        can_retry = (
            should_retry(result, task.retry_policy) and attempt < task.retry_policy.max_attempts - 1
        )

        # Repair + retry
        if can_retry and diagnosis.suggested_action == "repair" and diagnosis.repair is not None:
            self._apply_repair(task, diagnosis.repair)
            self._attempts[task_id] = attempt + 1
            self._state.transition_task(
                run.id,
                task_id,
                TaskStatus.RETRYING,
                attempt=attempt + 1,
                exit_code=result.exit_code,
                error=result.error,
            )
            delay = next_delay(attempt + 1, task.retry_policy)
            if delay.total_seconds() > 0:
                await asyncio.sleep(delay.total_seconds())
            sched.release(task_id)
            return False

        # Plain retry (e.g. MISSING_INPUT, NODE_FAIL)
        if can_retry and diagnosis.suggested_action == "retry":
            self._attempts[task_id] = attempt + 1
            self._state.transition_task(
                run.id,
                task_id,
                TaskStatus.RETRYING,
                attempt=attempt + 1,
                exit_code=result.exit_code,
                error=result.error,
            )
            delay = next_delay(attempt + 1, task.retry_policy)
            if delay.total_seconds() > 0:
                await asyncio.sleep(delay.total_seconds())
            sched.release(task_id)
            return False

        # Human / abort or no retry possible — mark as permanently failed
        self._state.transition_task(
            run.id,
            task_id,
            TaskStatus.FAILED,
            attempt=attempt,
            exit_code=result.exit_code,
            error=result.error,
        )
        sched.done(task_id)
        return diagnosis.suggested_action in ("human", "abort")

    @staticmethod
    def _get_task(workflow: Workflow, task_id: str) -> Task:
        """Return the Task object for *task_id* from the workflow."""
        for t in workflow.tasks:
            if t.id == task_id:
                return t
        msg = f"task {task_id!r} not found in workflow"
        raise ValueError(msg)

    @staticmethod
    def _apply_repair(task: Task, repair: RepairSpec) -> None:
        """Apply a RepairSpec to a Task (mutates task.resources in place)."""
        if repair.action == "increase_memory":
            current = task.resources.memory
            value, unit = Engine._parse_memory(current)
            factor = float(repair.params.get("factor", 2.0))
            new_value = max(1, int(value * factor))
            task.resources.memory = f"{new_value}{unit}"
        elif repair.action == "increase_walltime":
            if task.resources.walltime is not None:
                factor = float(repair.params.get("factor", 1.5))
                new_seconds = int(task.resources.walltime.total_seconds() * factor)
                task.resources.walltime = timedelta(seconds=new_seconds)

    @staticmethod
    def _parse_memory(memory: str) -> tuple[int, str]:
        """Parse '2GB' → (2, 'GB').  Supports MB/MiB/GB/GiB/TB/TiB."""
        memory = memory.strip()
        match = re.match(r"^(\d+)\s*(MB|MiB|GB|GiB|TB|TiB)$", memory)
        if not match:
            msg = f"cannot parse memory string: {memory!r}"
            raise ValueError(msg)
        return int(match.group(1)), match.group(2)
