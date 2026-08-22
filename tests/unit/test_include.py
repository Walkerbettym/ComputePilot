"""Tests for workflow include composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.workflow.schema import IncludeError, load_workflow


class TestIncludes:
    def test_flat_include(self, tmp_path: Path) -> None:
        (tmp_path / "prep.yaml").write_text(
            "name: p\ntasks:\n  - id: prep\n    command: echo prep\n    type: shell\n"
        )
        main = tmp_path / "main.yaml"
        main.write_text(
            "name: m\nincludes:\n  - prep.yaml\n"
            "tasks:\n  - id: go\n    command: echo go\n    type: shell\n"
            "    depends_on: [prep]\n"
        )
        wf = load_workflow(main)
        assert [t.id for t in wf.tasks] == ["prep", "go"]

    def test_nested_includes(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.yaml").write_text(
            "name: d\ntasks:\n  - id: deep_task\n    command: echo d\n    type: shell\n"
        )
        (tmp_path / "mid.yaml").write_text(
            "name: m\nincludes:\n  - sub/deep.yaml\n"
            "tasks:\n  - id: mid_task\n    command: echo m\n    type: shell\n"
        )
        main = tmp_path / "main.yaml"
        main.write_text("name: x\nincludes:\n  - mid.yaml\ntasks: []\n")
        wf = load_workflow(main)
        assert [t.id for t in wf.tasks] == ["deep_task", "mid_task"]

    def test_cycle_raises(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("name: a\nincludes:\n  - b.yaml\ntasks: []\n")
        (tmp_path / "b.yaml").write_text("name: b\nincludes:\n  - a.yaml\ntasks: []\n")
        with pytest.raises(IncludeError, match="cycle"):
            load_workflow(tmp_path / "a.yaml")

    def test_self_include_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "self.yaml"
        f.write_text("name: s\nincludes:\n  - self.yaml\ntasks: []\n")
        with pytest.raises(IncludeError, match="cycle"):
            load_workflow(f)

    def test_duplicate_ids_raise(self, tmp_path: Path) -> None:
        (tmp_path / "inc.yaml").write_text(
            "name: i\ntasks:\n  - id: dup\n    command: x\n    type: shell\n"
        )
        main = tmp_path / "main.yaml"
        main.write_text(
            "name: m\nincludes:\n  - inc.yaml\n"
            "tasks:\n  - id: dup\n    command: y\n    type: shell\n"
        )
        with pytest.raises(IncludeError, match="dup"):
            load_workflow(main)

    def test_non_mapping_include_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("- just\n- a list\n")
        main = tmp_path / "main.yaml"
        main.write_text("name: m\nincludes:\n  - bad.yaml\ntasks: []\n")
        with pytest.raises(IncludeError, match="mapping"):
            load_workflow(main)

    def test_params_apply_after_merge(self, tmp_path: Path) -> None:
        (tmp_path / "inc.yaml").write_text(
            "name: i\ntasks:\n  - id: t1\n    command: echo ${v}\n    type: shell\n"
        )
        main = tmp_path / "main.yaml"
        main.write_text("name: m\nincludes:\n  - inc.yaml\ntasks: []\n")
        wf = load_workflow(main, {"v": "merged"})
        assert wf.tasks[0].command == "echo merged"
