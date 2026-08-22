"""Demo 5: Composition + Reproducibility verify — includes, --set params, cpilot verify.

End-to-end flow:
  1. Build a main workflow that *includes* a common prep file and uses ${params}.
  2. Run it twice with the same parameters (via the Python API).
  3. Register outputs as artifacts for both runs.
  4. `cpilot verify` must judge them REPRODUCIBLE.
  5. Run once more with different parameters — verify must detect differences.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot import api
from computepilot.artifacts.store import ArtifactStore
from computepilot.runtime.state import StateStore
from computepilot.workflow.schema import IncludeError, load_workflow

MAIN_WF = """\
name: demo5_main
includes:
  - common/prep.yaml
tasks:
  - id: analyze
    command: echo seed=${seed} > out.txt
    type: shell
    depends_on: [prep_data]
"""

PREP_WF = """\
name: prep_steps
tasks:
  - id: prep_data
    command: echo preparing > prep.txt
    type: shell
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work = tmp_path / "proj"
    (work / "common").mkdir(parents=True)
    monkeypatch.chdir(work)
    (work / "main.yaml").write_text(MAIN_WF)
    (work / "common" / "prep.yaml").write_text(PREP_WF)
    state = tmp_path / "state"
    monkeypatch.setattr(api, "DEFAULT_STATE_DIR", state)
    return work


class TestDemo5CompositionAndVerify:
    def test_include_merges_and_runs(self, project: Path) -> None:
        wf = load_workflow("main.yaml", {"seed": "42"})
        ids = [t.id for t in wf.tasks]
        assert ids == ["prep_data", "analyze"]  # include first, own tasks after

        run = api.run("main.yaml", params={"seed": "42"})
        assert run.status.value == "succeeded"
        assert (Path.cwd() / "runs" / run.id / "prep.txt").exists()

    def test_include_cycle_detected(self, project: Path) -> None:
        (project / "common" / "prep.yaml").write_text(
            "name: p\nincludes:\n  - ../main.yaml\ntasks: []\n"
        )
        with pytest.raises(IncludeError, match="cycle"):
            load_workflow("main.yaml")

    def test_duplicate_ids_detected(self, project: Path) -> None:
        (project / "common" / "prep.yaml").write_text(
            "name: p\ntasks:\n  - id: analyze\n    command: dup\n"
        )
        with pytest.raises(IncludeError, match="analyze"):
            load_workflow("main.yaml")

    def test_verify_reproducible_then_different(self, project: Path) -> None:
        r1 = api.run("main.yaml", params={"seed": "42"})
        r2 = api.run("main.yaml", params={"seed": "42"})
        r3 = api.run("main.yaml", params={"seed": "43"})

        store = StateStore(api.DEFAULT_STATE_DIR / "state.db")
        for run in (r1, r2, r3):
            out = Path.cwd() / "runs" / run.id / "out.txt"
            ArtifactStore(store).register(run.id, "analyze", out, "result")
        store.close()

        assert api.verify(r1.id, r2.id)["reproducible"] is True
        result = api.verify(r1.id, r3.id)
        assert result["reproducible"] is False
        # seed only affects analyze's stdout, not registered artifacts; but task
        # exit codes match, so the difference must come from artifacts or tasks.
        assert any(c["category"] in ("artifact", "task") for c in result["checks"])
