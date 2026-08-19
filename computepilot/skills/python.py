"""Python skill definition."""

from __future__ import annotations

from computepilot.skills.base import ErrorAction, Skill

python_skill = Skill(
    name="python",
    version="0.1.0",
    description="Execute Python code, scripts, and manage packages",
    capabilities=[
        "run_python",
        "install_packages",
        "run_script",
        "run_notebook",
    ],
    constraints={
        "python_version": ">=3.11",
        "requires_pip": True,
    },
    error_handling={
        "ImportError": ErrorAction(action="install_package", params={"auto_install": True}),
        "ModuleNotFoundError": ErrorAction(action="install_package", params={"auto_install": True}),
        "SyntaxError": ErrorAction(action="report_error", params={"detail": "syntax_error"}),
    },
)
