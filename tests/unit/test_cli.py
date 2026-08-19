"""Test all CLI commands using CliRunner (isolated, no actual subprocess)."""
from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from computepilot.cli.main import app

# CLI requires typer which has a bug on Python 3.14
CLI_SKIP = pytest.mark.skipif(
    sys.version_info >= (3, 14),
    reason="typer incompatible with Python 3.14",
)

runner = CliRunner()


@CLI_SKIP
class TestCliBasic:
    def test_init_creates_file(self, tmp_path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "workflow.yaml").exists()

    def test_init_existing_path(self, tmp_path) -> None:
        (tmp_path / "workflow.yaml").write_text("")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 1  # already exists

    def test_validate_missing_file(self) -> None:
        result = runner.invoke(app, ["validate", "/nonexistent/workflow.yaml"])
        assert result.exit_code == 2

    def test_help_shows_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ["init", "validate", "run", "plan", "status", "logs", "resume", "cancel", "artifacts", "report", "skill"]:
            assert cmd in result.stdout

    def test_validate_invalid_yaml(self, tmp_path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("name: invalid\n")
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code in (1, 2)  # validation error


@CLI_SKIP
class TestCliSkill:
    def test_skill_list(self) -> None:
        result = runner.invoke(app, ["skill", "list"])
        assert result.exit_code == 0
        assert "python" in result.stdout

    def test_skill_add_missing(self) -> None:
        result = runner.invoke(app, ["skill", "add", "/nonexistent.yaml"])
        assert result.exit_code == 2


@CLI_SKIP
class TestCliRun:
    def test_run_missing_file(self) -> None:
        result = runner.invoke(app, ["run", "/nonexistent.yaml"])
        assert result.exit_code == 2


@CLI_SKIP
class TestCliStatus:
    def test_status_no_db(self, monkeypatch) -> None:
        import pathlib
        monkeypatch.setattr(pathlib.Path, "exists", lambda *a: False)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0


@CLI_SKIP
class TestCliLogs:
    def test_logs_no_db(self, monkeypatch) -> None:
        import pathlib
        monkeypatch.setattr(pathlib.Path, "exists", lambda *a: False)
        result = runner.invoke(app, ["logs", "some-run"])
        assert result.exit_code == 0


@CLI_SKIP
class TestCliCancel:
    def test_cancel_no_db(self, monkeypatch) -> None:
        import pathlib
        monkeypatch.setattr(pathlib.Path, "exists", lambda *a: False)
        result = runner.invoke(app, ["cancel", "some-run"])
        assert result.exit_code == 0


@CLI_SKIP
class TestCliArtifacts:
    def test_artifacts_no_db(self, monkeypatch) -> None:
        import pathlib
        monkeypatch.setattr(pathlib.Path, "exists", lambda *a: False)
        result = runner.invoke(app, ["artifacts", "some-run"])
        assert result.exit_code == 0


@CLI_SKIP
class TestCliReport:
    def test_report_no_db(self, monkeypatch) -> None:
        import pathlib
        monkeypatch.setattr(pathlib.Path, "exists", lambda *a: False)
        result = runner.invoke(app, ["report", "some-run"])
        assert result.exit_code == 0


@CLI_SKIP
class TestCliResume:
    def test_resume_missing_file(self) -> None:
        result = runner.invoke(app, ["resume", "some-run"])
        assert result.exit_code == 2