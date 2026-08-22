"""Tests for cpilot dag — ascii/mermaid/json rendering."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
import typer

from computepilot.cli.commands import dag as dag_cmd
from computepilot.models.run import Run, RunStatus, TaskStatus
from computepilot.runtime.state import StateStore

LINEAR_YAML = """\

name: linear

tasks:

  - id: fetch

    command: echo fetch

    type: shell

  - id: process

    command: echo process

    type: shell

    depends_on: [fetch]

  - id: store

    command: echo store

    type: shell

    depends_on: [process]

"""


DIAMOND_YAML = """\

name: diamond

tasks:

  - id: root

    command: echo root

    type: shell

  - id: left

    command: echo left

    type: shell

    depends_on: [root]

  - id: right

    command: echo right

    type: shell

    depends_on: [root]

  - id: join

    command: echo join

    type: shell

    depends_on: [left, right]

"""


CYCLE_YAML = """\

name: cyclic

tasks:

  - id: a

    command: x

    type: shell

    depends_on: [b]

  - id: b

    command: y

    type: shell

    depends_on: [a]

"""


class TestDagCmd:
    def test_ascii_linear(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(LINEAR_YAML)

        dag_cmd.render_dag(str(wf), format="ascii", output=None, run_id=None)

        out = capsys.readouterr().out

        assert "linear (3 tasks)" in out

        assert "└── process" in out and "└── store" in out

    def test_ascii_diamond_marks_repeat(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(DIAMOND_YAML)

        dag_cmd.render_dag(str(wf), format="ascii", output=None, run_id=None)

        out = capsys.readouterr().out

        assert "join" in out and "↺" in out

    def test_mermaid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(DIAMOND_YAML)

        dag_cmd.render_dag(str(wf), format="mermaid", output=None, run_id=None)

        out = capsys.readouterr().out

        assert "graph TD" in out

        assert 'root["root<br/>shell, cpu=1"]' in out

        assert "root --> left" in out and "right --> join" in out

    def test_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(LINEAR_YAML)

        dag_cmd.render_dag(str(wf), format="json", output=None, run_id=None)

        data = json.loads(capsys.readouterr().out)

        assert data["workflow"] == "linear"

        assert [n["id"] for n in data["nodes"]] == ["fetch", "process", "store"]

        assert {"from": "fetch", "to": "process"} in [
            {"from": e["from"], "to": e["to"]} for e in data["edges"]
        ]

        assert data["topological_order"] == ["fetch", "process", "store"]

    def test_cycle_exits_1(self, tmp_path: Path) -> None:

        wf = tmp_path / "cyc.yaml"

        wf.write_text(CYCLE_YAML)

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag(str(wf), format="ascii", output=None, run_id=None)

        assert ei.value.exit_code == 1

    def test_missing_file(self) -> None:

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag("/nonexistent/wf.yaml", format="ascii", output=None, run_id=None)

        assert ei.value.exit_code == 2

    def test_bad_format(self, tmp_path: Path) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(LINEAR_YAML)

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag(str(wf), format="png", output=None, run_id=None)

        assert ei.value.exit_code == 2


class TestDagSvg:
    def test_svg_to_file(self, tmp_path: Path) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(LINEAR_YAML)

        out = tmp_path / "sub" / "graph.svg"

        dag_cmd.render_dag(str(wf), format="svg", output=str(out), run_id=None)

        text = out.read_text()

        assert text.startswith("<svg") and text.endswith("</svg>")

        assert 'xmlns="http://www.w3.org/2000/svg"' in text

        assert "fetch" in text and "store" in text

    def test_svg_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:

        wf = tmp_path / "wf.yaml"

        wf.write_text(DIAMOND_YAML)

        dag_cmd.render_dag(str(wf), format="svg", output=None, run_id=None)

        out = capsys.readouterr().out

        assert "<svg" in out and "join" in out

    def test_svg_cycle_exits_1(self, tmp_path: Path) -> None:

        wf = tmp_path / "cyc.yaml"

        wf.write_text(CYCLE_YAML)

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag(str(wf), format="svg", output=None, run_id=None)

        assert ei.value.exit_code == 1


# -- v1.0: dag --run -------------------------------------------------------------


class TestDagFromRun:
    @pytest.fixture
    def run_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:

        home = tmp_path / "home"

        home.mkdir()

        monkeypatch.setattr(Path, "home", lambda: home)

        db = home / ".local/share/computepilot/state.db"

        store = StateStore(db)

        store.create_run(
            Run(
                id="r_dag",
                workflow_id=uuid4(),
                workflow_sha256="x",
                status=RunStatus.SUCCEEDED,
                config={
                    "total_tasks": 3,
                    "workflow": {
                        "tasks": [
                            {"id": "a", "type": "shell", "depends_on": []},
                            {"id": "b", "type": "shell", "depends_on": ["a"]},
                            {"id": "c", "type": "shell", "depends_on": ["b"]},
                        ]
                    },
                },
            )
        )

        store.transition_task("r_dag", "a", TaskStatus.SUCCEEDED, exit_code=0)

        store.transition_task("r_dag", "b", TaskStatus.FAILED, exit_code=2)

        store.close()

        return db

    def test_ascii_with_status(self, run_db: Path, capsys: pytest.CaptureFixture[str]) -> None:

        dag_cmd.render_dag("", format="ascii", output=None, run_id="r_dag")

        out = capsys.readouterr().out

        assert "✓ a" in out and "[succeeded]" in out

        assert "✗ b" in out and "c" in out

    def test_svg_status_colors(self, run_db: Path, capsys: pytest.CaptureFixture[str]) -> None:

        dag_cmd.render_dag("", format="svg", output=None, run_id="r_dag")

        out = capsys.readouterr().out

        assert "<svg" in out and "#12351f" in out and "#3d1418" in out

    def test_json_statuses(self, run_db: Path, capsys: pytest.CaptureFixture[str]) -> None:

        dag_cmd.render_dag("", format="json", output=None, run_id="r_dag")

        data = json.loads(capsys.readouterr().out)

        assert data["statuses"]["a"] == "succeeded"

        assert len(data["nodes"]) == 3

    def test_unknown_run(self, run_db: Path) -> None:

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag("", format="ascii", output=None, run_id="ghost")

        assert ei.value.exit_code == 2

    def test_old_run_without_structure(self, run_db: Path) -> None:

        from computepilot.runtime.state import StateStore

        store = StateStore(run_db)

        store.create_run(
            Run(id="r_old_fmt", workflow_id=uuid4(), workflow_sha256="x", status=RunStatus.CREATED)
        )

        store.close()

        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag("", format="ascii", output=None, run_id="r_old_fmt")

        assert ei.value.exit_code == 2
