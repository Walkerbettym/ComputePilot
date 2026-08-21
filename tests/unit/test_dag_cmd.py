"""Tests for cpilot dag — ascii/mermaid/json rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from computepilot.cli.commands import dag as dag_cmd

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
        dag_cmd.render_dag(str(wf), format="ascii", output=None)
        out = capsys.readouterr().out
        assert "linear (3 tasks)" in out
        assert "└── process" in out and "└── store" in out

    def test_ascii_diamond_marks_repeat(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(DIAMOND_YAML)
        dag_cmd.render_dag(str(wf), format="ascii", output=None)
        out = capsys.readouterr().out
        assert "join" in out and "↺" in out

    def test_mermaid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(DIAMOND_YAML)
        dag_cmd.render_dag(str(wf), format="mermaid", output=None)
        out = capsys.readouterr().out
        assert "graph TD" in out
        assert 'root["root<br/>shell, cpu=1"]' in out
        assert "root --> left" in out and "right --> join" in out

    def test_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(LINEAR_YAML)
        dag_cmd.render_dag(str(wf), format="json", output=None)
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
            dag_cmd.render_dag(str(wf), format="ascii", output=None)
        assert ei.value.exit_code == 1

    def test_missing_file(self) -> None:
        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag("/nonexistent/wf.yaml", format="ascii", output=None)
        assert ei.value.exit_code == 2

    def test_bad_format(self, tmp_path: Path) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(LINEAR_YAML)
        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag(str(wf), format="png", output=None)
        assert ei.value.exit_code == 2


class TestDagSvg:
    def test_svg_to_file(self, tmp_path: Path) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(LINEAR_YAML)
        out = tmp_path / "sub" / "graph.svg"
        dag_cmd.render_dag(str(wf), format="svg", output=str(out))
        text = out.read_text()
        assert text.startswith("<svg") and text.endswith("</svg>")
        assert 'xmlns="http://www.w3.org/2000/svg"' in text
        assert "fetch" in text and "store" in text

    def test_svg_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        wf = tmp_path / "wf.yaml"
        wf.write_text(DIAMOND_YAML)
        dag_cmd.render_dag(str(wf), format="svg", output=None)
        out = capsys.readouterr().out
        assert "<svg" in out and "join" in out

    def test_svg_cycle_exits_1(self, tmp_path: Path) -> None:
        wf = tmp_path / "cyc.yaml"
        wf.write_text(CYCLE_YAML)
        with pytest.raises(typer.Exit) as ei:
            dag_cmd.render_dag(str(wf), format="svg", output=None)
        assert ei.value.exit_code == 1
