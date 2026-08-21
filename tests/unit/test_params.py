"""Tests for workflow parameter substitution (${key} / ${key:-default})."""

from __future__ import annotations

from pathlib import Path

import pytest

from computepilot.workflow.params import (
    MissingParameterError,
    parse_set_args,
    substitute,
    substitute_workflow_data,
)
from computepilot.workflow.schema import load_workflow

PARAM_YAML = """\
name: param_wf
defaults:
  cpu: 1
tasks:
  - id: t1
    command: echo ${msg} > ${outfile:-out.txt}
    type: shell
    environment:
      TAG: ${tag:-dev}
"""


class TestSubstitute:
    def test_basic_replacement(self) -> None:
        assert substitute("hello ${name}", {"name": "world"}) == "hello world"

    def test_default_used_when_missing(self) -> None:
        assert substitute("${a:-x}${b}", {"b": "y"}) == "xy"

    def test_param_overrides_default(self) -> None:
        assert substitute("${a:-x}", {"a": "z"}) == "z"

    def test_missing_raises_with_key(self) -> None:
        with pytest.raises(MissingParameterError) as ei:
            substitute("${gone}", {})
        assert ei.value.missing == ["gone"]

    def test_multiple_placeholders(self) -> None:
        assert substitute("${x}-${y:-2}", {"x": "1"}) == "1-2"


class TestWorkflowData:
    def test_collects_all_missing_keys(self) -> None:
        data = {"tasks": [{"id": "a", "command": "${p} ${q:-d}"}]}
        with pytest.raises(MissingParameterError) as ei:
            substitute_workflow_data(data, {})
        assert ei.value.missing == ["p"]

    def test_nested_structures(self) -> None:
        data = {
            "tasks": [
                {
                    "id": "a",
                    "command": "run ${v}",
                    "args": ["--flag", "${w:-def}"],
                    "environment": {"K": "${k}"},
                }
            ]
        }
        out = substitute_workflow_data(data, {"v": "V", "k": "KV"})
        assert out["tasks"][0]["command"] == "run V"
        assert out["tasks"][0]["args"] == ["--flag", "def"]
        assert out["tasks"][0]["environment"] == {"K": "KV"}


class TestParseSetArgs:
    def test_valid_pairs(self) -> None:
        assert parse_set_args(["a=1", "b=two=parts"]) == {"a": "1", "b": "two=parts"}

    def test_none_gives_empty(self) -> None:
        assert parse_set_args(None) == {}

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="--set"):
            parse_set_args(["noequals"])

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_set_args(["=v"])


class TestLoadWorkflowParams:
    def test_substitution_applied(self, tmp_path: Path) -> None:
        wf_file = tmp_path / "wf.yaml"
        wf_file.write_text(PARAM_YAML)
        wf = load_workflow(wf_file, {"msg": "hi"})
        assert wf.tasks[0].command == "echo hi > out.txt"
        assert wf.tasks[0].environment["TAG"] == "dev"

    def test_missing_required_fails(self, tmp_path: Path) -> None:
        wf_file = tmp_path / "wf.yaml"
        wf_file.write_text(PARAM_YAML)
        with pytest.raises(MissingParameterError):
            load_workflow(wf_file, {})

    def test_no_params_keeps_literal(self, tmp_path: Path) -> None:
        wf_file = tmp_path / "wf.yaml"
        plain = PARAM_YAML.replace("${msg}", "fixed")
        wf_file.write_text(plain)
        wf = load_workflow(wf_file)
        assert "fixed" in wf.tasks[0].command
