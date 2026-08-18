"""Shell skill definition."""

from __future__ import annotations

from sciflow.skills.base import Skill

shell_skill = Skill(
    name="shell",
    version="0.1.0",
    description="Run shell commands, scripts, and pipelines",
    capabilities=[
        "run_shell_command",
        "pipe_redirect",
        "run_bash_script",
        "environment_setup",
    ],
    constraints={
        "shell": "/bin/bash",
        "timeout_seconds": 3600,
    },
    error_handling={
        "non_zero_exit": {"action": "capture_stderr", "params": {"max_retries": 0}},
        "timeout": {"action": "kill_process", "params": {"signal": "SIGTERM"}},
    },
)
