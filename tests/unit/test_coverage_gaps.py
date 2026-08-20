"""Coverage gap fill: provider, probe, provenance, planner edge cases."""
from __future__ import annotations

from uuid import uuid4

from computepilot.agent.intent import Intent
from computepilot.agent.planner import Planner
from computepilot.agent.provider import OpenAIProvider
from computepilot.artifacts.provenance import ProvenanceBuilder
from computepilot.models.run import Run, RunStatus
from computepilot.models.workflow import Resources, Task, TaskType
from computepilot.runtime.probe import EnvironmentProbe, ProbeResult, apply_probe_result


class TestProviderEdgeCases:
    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("COMPUTEPILOT_LLM_API_KEY", "from-env")
        p = OpenAIProvider()
        assert p._api_key == "from-env"

    def test_custom_model(self):
        p = OpenAIProvider(api_key="k", model="custom-model")
        assert p._model == "custom-model"

    def test_custom_base_url(self):
        p = OpenAIProvider(api_key="k", base_url="https://example.com/v2")
        assert p._base_url == "https://example.com/v2"


class TestProbeEdgeCases:
    def test_empty_probe(self):
        p = EnvironmentProbe()
        r = p.probe()
        assert r.available_vcpus >= 1
        assert r.data_size_bytes == 0

    def test_probe_with_large_file(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_text("x" * 5 * 1024 * 1024)
        p = EnvironmentProbe()
        r = p.probe(data_paths=[str(f)])
        assert r.data_size_bytes >= 5 * 1024 * 1024
        assert r.data_file_count >= 1

    def test_probe_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        p = EnvironmentProbe()
        r = p.probe(data_paths=[str(d)])
        assert r.data_size_bytes == 0

    def test_apply_no_data(self):
        task = Task(id="t", command="echo", resources=Resources(cpu=4, memory="4GB"))
        probe = ProbeResult(available_vcpus=8, data_size_bytes=0)
        apply_probe_result([task], probe)
        assert task.resources.cpu == 4
        assert task.resources.memory == "4GB"


class TestProvenanceEdgeCases:
    def test_manifest_structure(self):
        run = Run(id="r1", workflow_id=uuid4(), workflow_sha256="abc", status=RunStatus.CREATED)
        b = ProvenanceBuilder(run)
        m = b.build_manifest()
        assert m["run_id"] == "r1"
        assert m["code"]["type"] in ("git", "unknown")
        assert m["schema_version"] == 1


class TestPlannerEdgeCases:
    def test_python_type(self):
        wf = Planner().plan(Intent(verb="train", target="model"))
        assert wf.tasks[0].type == TaskType.PYTHON

    def test_shell_type(self):
        wf = Planner().plan(Intent(verb="shell", target="deploy.sh"))
        assert wf.tasks[0].type == TaskType.SHELL

    def test_docker_type(self):
        wf = Planner().plan(Intent(verb="docker", target="container"))
        assert wf.tasks[0].type == TaskType.DOCKER

    def test_parameters_passed(self):
        wf = Planner().plan(Intent(
            verb="run", target="test",
            parameters={"epochs": 10, "lr": 0.01},
        ))
        assert wf.tasks[0].resources.cpu == 1  # default

    def test_custom_resources(self):
        wf = Planner().plan(Intent(
            verb="run", target="test",
            resources={"cpu": 8, "memory": "16GB"},
        ))
        assert wf.tasks[0].resources.cpu == 8
        assert wf.tasks[0].resources.memory == "16GB"
