"""Slurm skill definition."""

from __future__ import annotations

from sciflow.skills.base import ErrorAction, Skill

slurm_skill = Skill(
    name="slurm",
    version="0.1.0",
    description="Submit and manage Slurm batch jobs on HPC clusters",
    capabilities=[
        "submit_batch_job",
        "monitor_job",
        "cancel_job",
        "query_queue",
        "allocate_resources",
    ],
    constraints={
        "required_commands": ["sbatch", "squeue", "scancel"],
        "partition": None,
    },
    error_handling={
        "job_failed": ErrorAction(
            action="fetch_logs", params={"tail_lines": 50}
        ),
        "node_failure": ErrorAction(
            action="resubmit",
            params={"max_retries": 3, "backoff": "linear"},
        ),
        "time_limit": ErrorAction(
            action="resubmit",
            params={"max_retries": 1, "extend_time": True},
        ),
    },
)

