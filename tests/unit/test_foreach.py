"""Tests for foreach task fan-out expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.workflow.expand import ForeachError, expand_foreach
from computepilot.workflow.schema import load_workflow

SWEEP_YAML = """\
name: sweep
tasks:
  - id: setup
    command: echo ready
    type: shell
  - id: simulate
    foreach:
      values: [10, 20, 30]
      as: n
    command: echo n=${n} > run_${n}.txt
    type: shell
    environment:
      TAG: case_${n}
    depends_on: [setup]
  - id: gather
    command: echo done
    type: shell
    depends_on: [simulate]
"""


class TestExpandForeach:
    def test_basic_expansion(self) -> None:
        raw = {
            "tasks": [
                {
                    "id": "t",
                    "command": "echo ${v}",
                    "type": "shell",
                    "foreach": {"values": [1, 2], "as": "v"},
                },
            ]
        }
        out = expand_foreach(raw)
        ids = [t["id"] for t in out["tasks"]]
        assert ids == ["t_0", "t_1"]
        assert out["tasks"][0]["command"] == "echo 1"
        assert out["tasks"][1]["command"] == "echo 2"

    def test_fields_and_env_substituted(self) -> None:
        data = load_workflow_data(SWEEP_YAML)
        sims = [t for t in data["tasks"] if t["id"].startswith("simulate_")]
        assert len(sims) == 3
        assert sims[0]["command"] == "echo n=10 > run_10.txt"
        assert sims[0]["environment"]["TAG"] == "case_10"
        assert sims[2]["environment"]["TAG"] == "case_30"

    def test_depends_on_rewritten(self) -> None:
        data = load_workflow_data(SWEEP_YAML)
        by_id = {t["id"]: t for t in data["tasks"]}
        assert by_id["simulate_0"]["depends_on"] == ["setup"]
        assert set(by_id["gather"]["depends_on"]) == {"simulate_0", "simulate_1", "simulate_2"}

    def test_no_values_raises(self) -> None:
        raw = {"tasks": [{"id": "t", "command": "x", "foreach": {"values": [], "as": "v"}}]}
        with pytest.raises(ForeachError):
            expand_foreach(raw)

    def test_missing_id_raises(self) -> None:
        raw = {"tasks": [{"command": "x", "foreach": {"values": [1]}}]}
        with pytest.raises(ForeachError, match="missing 'id'"):
            expand_foreach(raw)

    def test_fanout_cap(self) -> None:
        raw = {
            "tasks": [
                {
                    "id": "t",
                    "command": "x",
                    "type": "shell",
                    "foreach": {"values": list(range(501)), "as": "i"},
                },
            ]
        }
        with pytest.raises(ForeachError, match="500"):
            expand_foreach(raw)

    def test_params_resolved_before_expansion(self, tmp_path: Path) -> None:
        wf_file = tmp_path / "wf.yaml"
        wf_file.write_text(
            "name: p\ntasks:\n"
            '  - id: job\n    foreach:\n      values: ["${a}", "${b}"]\n      as: x\n'
            "    command: echo ${x}\n    type: shell\n"
        )
        wf = load_workflow(wf_file, {"a": "hello", "b": "world"})
        cmds = sorted(t.command for t in wf.tasks)
        assert cmds == ["echo hello", "echo world"]

    def test_e2e_run_expanded_workflow(self, tmp_path: Path, monkeypatch) -> None:
        from computepilot import api

        work = tmp_path / "w"
        work.mkdir()
        monkeypatch.chdir(work)
        (work / "wf.yaml").write_text(SWEEP_YAML)
        state = tmp_path / "state"
        monkeypatch.setattr(api, "DEFAULT_STATE_DIR", state)

        run = api.run("wf.yaml")
        assert run.status.value == "succeeded"
        st = api.status(run.id, state_dir=state)
        task_ids = {t["task_id"] for t in st["tasks"]}
        assert task_ids == {"setup", "simulate_0", "simulate_1", "simulate_2", "gather"}


def load_workflow_data(yaml_text: str) -> dict:
    """Load raw expanded workflow data via the public schema pipeline."""
    import yaml as _yaml

    from computepilot.workflow.expand import expand_foreach as _exp

    raw = _yaml.safe_load(yaml_text)
    return _exp(raw)
