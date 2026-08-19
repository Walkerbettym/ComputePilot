"""Docker skill definition."""

from __future__ import annotations

from sciflow.skills.base import ErrorAction, Skill

docker_skill = Skill(
    name="docker",
    version="0.1.0",
    description="Build, run, and manage Docker containers",
    capabilities=[
        "run_container",
        "pull_image",
        "build_image",
        "push_image",
        "manage_volumes",
        "manage_networks",
    ],
    constraints={
        "required_commands": ["docker"],
        "privileged": False,
    },
    error_handling={
        "image_not_found": ErrorAction(action="pull_image", params={"auto_pull": True}),
        "port_conflict": ErrorAction(
            action="retry", params={"max_retries": 3, "port_offset": True}
        ),
        "disk_full": ErrorAction(action="cleanup", params={"prune": True}),
    },
)
