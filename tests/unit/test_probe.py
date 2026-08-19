"""Tests for EnvironmentProbe and deferred DAG generation."""

from __future__ import annotations

from pathlib import Path

from computepilot.models.workflow import Resources, Task
from computepilot.runtime.probe import EnvironmentProbe, ProbeResult, apply_probe_result


class TestProbeBasic:
    def test_probe_empty(self) -> None:
        """Probe with no data paths returns defaults."""
        probe = EnvironmentProbe()
        result = probe.probe(estimate_tasks=10)
        assert result.estimated_tasks == 10
        assert result.available_vcpus >= 1
        assert result.data_size_bytes == 0

    def test_probe_with_data_file(self, tmp_path: Path) -> None:
        """Probe measures file sizes correctly."""
        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b,c\n1,2,3\n" * 1000)

        probe = EnvironmentProbe()
        result = probe.probe(data_paths=[str(data_file)])
        assert result.data_size_bytes > 0
        assert result.data_file_count >= 1
        assert data_file.name in result.data_paths[0]

    def test_probe_data_size_properties(self) -> None:
        """ProbeResult size properties work."""
        result = ProbeResult(
            data_size_bytes=2 * 1024 * 1024 * 1024,  # 2 GB
            available_vcpus=8,
        )
        assert abs(result.data_size_gb - 2.0) < 0.01
        assert abs(result.data_size_mb - 2048.0) < 1.0

    def test_suggested_parallelism(self) -> None:
        """Parallelism suggestion uses data and CPU."""
        result = ProbeResult(
            data_size_bytes=500 * 1024 * 1024,  # 500 MB
            available_vcpus=16,
        )
        # 500MB / 500MB per CPU = 1; capped by 16 = 1
        assert result.suggested_parallelism >= 1


class TestApplyProbeResult:
    def test_apply_probe_adjusts_cpu(self) -> None:
        """Task CPU is capped by available vCPUs."""
        task = Task(id="t", command="echo", resources=Resources(cpu=64))
        tasks = [task]
        probe = ProbeResult(available_vcpus=8, data_size_bytes=0)
        apply_probe_result(tasks, probe)
        assert tasks[0].resources.cpu <= 8

    def test_apply_probe_large_data_adjusts_memory(self) -> None:
        """Large data triggers memory increase."""
        task = Task(id="t", command="echo", resources=Resources(memory="2GB"))
        tasks = [task]
        probe = ProbeResult(
            data_size_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
            available_vcpus=16,
        )
        apply_probe_result(tasks, probe)
        assert int(tasks[0].resources.memory.replace("GB", "")) >= 15
