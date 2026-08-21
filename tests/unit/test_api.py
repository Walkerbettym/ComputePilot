"""Tests for the computepilot.api Python layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot import api
from computepilot.workflow.params import MissingParameterError

WF = """\
name: api_demo
tasks:
  - id: gen
    command: echo ${word:-hello} > out.txt
    type: shell
"""


@pytest.fixture
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "wf.yaml").write_text(WF)
    state = tmp_path / "state"
    monkeypatch.setattr(api, "DEFAULT_STATE_DIR", state)
    return state


class TestApiRun:
    def test_run_returns_succeeded_run(self, ws: Path) -> None:
        run = api.run("wf.yaml", state_dir=ws)
        assert run.status.value == "succeeded"
        assert (Path.cwd() / "runs" / run.id / "out.txt").exists()

    def test_run_with_params(self, ws: Path) -> None:
        run = api.run("wf.yaml", params={"word": "custom"}, state_dir=ws)
        out = (Path.cwd() / "runs" / run.id / "out.txt").read_text().strip()
        assert out == "custom"

    def test_missing_param_raises(self, ws: Path) -> None:
        strict = ws.parent / "strict.yaml"
        strict.write_text(
            "name: s\ntasks:\n  - id: a\n    command: echo ${need}\n    type: shell\n"
        )
        with pytest.raises(MissingParameterError):
            api.run(strict, params={}, state_dir=ws)

    def test_invalid_workflow_raises(self, ws: Path) -> None:
        bad = ws.parent / "bad.yaml"
        bad.write_text(
            "name: b\ntasks:\n"
            "  - id: a\n    command: x\n    type: shell\n    depends_on: [b]\n"
            "  - id: b\n    command: y\n    type: shell\n    depends_on: [a]\n"
        )
        with pytest.raises(ValueError, match="validation failed"):
            api.run(bad, state_dir=ws)


class TestApiQueries:
    def test_status_and_list(self, ws: Path) -> None:
        run = api.run("wf.yaml", state_dir=ws)
        st = api.status(run.id, state_dir=ws)
        assert st["run"]["id"] == run.id
        assert st["tasks"][0]["task_id"] == "gen"
        runs = api.list_runs(state_dir=ws)
        assert any(r["id"] == run.id for r in runs)

    def test_status_unknown_raises(self, ws: Path) -> None:
        with pytest.raises(KeyError):
            api.status("ghost", state_dir=ws)

    def test_artifacts_roundtrip(self, ws: Path) -> None:
        from computepilot.artifacts.store import ArtifactStore
        from computepilot.runtime.state import StateStore

        run = api.run("wf.yaml", state_dir=ws)
        store = StateStore(ws / "state.db")
        ArtifactStore(store).register(
            run.id, "gen", Path.cwd() / "runs" / run.id / "out.txt", "result"
        )
        store.close()
        arts = api.artifacts(run.id, state_dir=ws)
        assert len(arts) == 1 and arts[0]["type"] == "result"

    def test_report_writes_files(self, ws: Path, tmp_path: Path) -> None:
        run = api.run("wf.yaml", state_dir=ws)
        dest = tmp_path / "report_out"
        result = api.report(run.id, out_dir=dest, state_dir=ws)
        assert result == dest
        assert (dest / "manifest.json").exists()
        assert (dest / "report.md").exists()

    def test_cancel_marks_cancelled(self, ws: Path) -> None:
        run = api.run("wf.yaml", state_dir=ws)
        api.cancel(run.id, state_dir=ws)
        assert api.status(run.id, state_dir=ws)["run"]["status"] == "cancelled"


class TestApiVerify:
    def test_identical_runs_reproducible(self, ws: Path) -> None:
        r1 = api.run("wf.yaml", state_dir=ws)
        r2 = api.run("wf.yaml", state_dir=ws)
        result = api.verify(r1.id, r2.id, state_dir=ws)
        assert result["reproducible"] is True

    def test_different_params_not_reproducible(self, ws: Path) -> None:
        r1 = api.run("wf.yaml", params={"word": "aaa"}, state_dir=ws)
        r2 = api.run("wf.yaml", params={"word": "bbb"}, state_dir=ws)
        # register artifacts so checksums are compared too
        from computepilot.artifacts.store import ArtifactStore
        from computepilot.runtime.state import StateStore

        store = StateStore(ws / "state.db")
        for r in (r1, r2):
            ArtifactStore(store).register(
                r.id, "gen", Path.cwd() / "runs" / r.id / "out.txt", "result"
            )
        store.close()
        result = api.verify(r1.id, r2.id, state_dir=ws)
        assert result["reproducible"] is False
        categories = {c["category"] for c in result["checks"]}
        assert "artifact" in categories

    def test_unknown_run_raises(self, ws: Path) -> None:
        r = api.run("wf.yaml", state_dir=ws)
        with pytest.raises(KeyError):
            api.verify(r.id, "ghost", state_dir=ws)


class TestApiResume:
    def test_resume_completes(self, ws: Path) -> None:
        run = api.run("wf.yaml", state_dir=ws)
        again = api.resume(run.id, "wf.yaml", state_dir=ws)
        assert again.status.value == "succeeded"
