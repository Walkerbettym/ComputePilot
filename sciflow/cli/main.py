"""ComputePilot CLI — entry point."""

from __future__ import annotations

import typer

from sciflow.cli.commands import init, logs, run, status, validate

app = typer.Typer(
    name="sciflow",
    help="Agentic workflow runtime for reproducible scientific computing",
    no_args_is_help=True,
)

app.command(name="init")(init.init)
app.command(name="validate")(validate.validate_workflow)
app.command(name="run")(run.run)
app.command(name="status")(status.status)
app.command(name="logs")(logs.logs)

if __name__ == "__main__":
    app()
