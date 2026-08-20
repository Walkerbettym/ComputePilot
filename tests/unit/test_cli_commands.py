"""CLI command tests using typer.testing.CliRunner (skip on Python 3.14+)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CLI_SKIP = pytest.mark.skipif(
    sys.version_info >= (3, 14), reason="typer incompatible with Python 3.14"
)


@CLI_SKIP
class TestCliBasic:
    def _invoke(self, args: list[str]):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_help(self):
        r = self._invoke(["--help"])
        assert r.exit_code == 0

    def test_init(self, tmp_path: Path):
        r = self._invoke(["init", str(tmp_path)])
        assert r.exit_code == 0
        assert (tmp_path / "workflow.yaml").exists()

    def test_init_existing(self, tmp_path: Path):
        (tmp_path / "workflow.yaml").write_text("")
        r = self._invoke(["init", str(tmp_path)])
        assert r.exit_code == 1

    def test_validate_missing(self):
        r = self._invoke(["validate", "/nonexistent.yaml"])
        assert r.exit_code == 2


@CLI_SKIP
class TestCliStatus:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_status_no_db(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["status"])
        assert r.exit_code == 0


@CLI_SKIP
class TestCliLogs:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_logs_no_db(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["logs", "some-run"])
        assert r.exit_code == 0


@CLI_SKIP
class TestCliCancel:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_cancel_no_db(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["cancel", "some-run"])
        assert r.exit_code == 0


@CLI_SKIP
class TestCliArtifacts:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_artifacts_no_db(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["artifacts", "some-run"])
        assert r.exit_code == 0


@CLI_SKIP
class TestCliReport:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_report_no_db(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["report", "some-run"])
        assert r.exit_code == 0


@CLI_SKIP
class TestCliResume:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_resume_missing(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda _: False)
        r = self._invoke(["resume", "some-run"])
        assert r.exit_code == 2


@CLI_SKIP
class TestCliSkill:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_skill_list(self):
        r = self._invoke(["skill", "list"])
        assert r.exit_code == 0

    def test_skill_add_missing(self):
        r = self._invoke(["skill", "add", "/nonexistent.yaml"])
        assert r.exit_code == 2


@CLI_SKIP
class TestCliRun:
    def _invoke(self, args):
        from typer.testing import CliRunner

        from computepilot.cli.main import app

        return CliRunner().invoke(app, args)

    def test_run_missing(self):
        r = self._invoke(["run", "/nonexistent.yaml"])
        assert r.exit_code == 2
