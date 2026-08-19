"""Environment probe — measure actual infrastructure metrics for deferred DAG generation.

Implements the paper's "deferred workflow generation" concept:
phase 1 generates a plan with estimates, phase 2 probes the actual
environment, phase 3 generates the final DAG grounded in real measurements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProbeResult:
    """Measured infrastructure metrics for deferred DAG generation."""

    # Data stage
    data_size_bytes: int = 0
    data_file_count: int = 0
    data_paths: list[str] = field(default_factory=list)

    # Compute resources
    available_vcpus: int = 0
    available_memory_bytes: int = 0
    available_gpus: int = 0

    # Input parameters (passed through from the plan)
    parallelism: int = 1
    estimated_tasks: int = 0

    @property
    def data_size_mb(self) -> float:
        """Data size in megabytes."""
        return self.data_size_bytes / (1024 * 1024)

    @property
    def data_size_gb(self) -> float:
        """Data size in gigabytes."""
        return self.data_size_bytes / (1024 * 1024 * 1024)

    @property
    def suggested_parallelism(self) -> int:
        """Suggest parallelism based on available vCPUs and data size."""
        if self.data_size_bytes == 0:
            return self.available_vcpus
        # Scale: 1 task per 500MB per CPU, but not more than vCPUs
        by_data = max(1, int(self.data_size_mb / 500))
        by_cpu = max(1, self.available_vcpus)
        return min(by_data, by_cpu)


class EnvironmentProbe:
    """Measure the execution environment for deferred DAG generation.

    Usage::

        probe = EnvironmentProbe()
        result = probe.probe(
            data_paths=["/data/input", "/data/reference"],
            estimate_tasks=50,
        )
        print(f"Data: {result.data_size_gb:.2f} GB, CPUs: {result.available_vcpus}")
    """

    def probe(
        self,
        data_paths: list[str] | None = None,
        estimate_tasks: int = 1,
        parallelism: int = 1,
    ) -> ProbeResult:
        """Measure available resources and data sizes.

        Args:
            data_paths: Directories/files to measure for data staging.
            estimate_tasks: Estimated number of workflow tasks.
            parallelism: Desired parallelism level.

        Returns:
            A :class:`ProbeResult` with measured metrics.
        """
        # 1. Measure data
        total_bytes = 0
        file_count = 0
        resolved_paths: list[str] = []

        for path_str in data_paths or []:
            p = Path(path_str)
            if not p.exists():
                continue
            resolved_paths.append(str(p.resolve()))
            if p.is_file():
                total_bytes += p.stat().st_size
                file_count += 1
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        total_bytes += f.stat().st_size
                        file_count += 1
                        resolved_paths.append(str(f.resolve()))

        # 2. Measure available CPUs
        try:
            avcpus = len(os.sched_getaffinity(0))
        except AttributeError:
            avcpus = os.cpu_count() or 1

        # 3. Measure available memory
        try:
            import resource

            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            avmem = 8 * 1024 * 1024 * 1024 if soft == resource.RLIM_INFINITY else soft
        except (OSError, ImportError, AttributeError):
            avmem = 8 * 1024 * 1024 * 1024

        # 4. Check GPUs
        avgpus = 0
        import subprocess as _sp

        try:
            r = _sp.run(
                ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                avgpus = int(r.stdout.strip())
        except (FileNotFoundError, _sp.TimeoutExpired, ValueError, OSError):
            avgpus = 0

        return ProbeResult(
            data_size_bytes=total_bytes,
            data_file_count=file_count,
            data_paths=resolved_paths,
            available_vcpus=avcpus,
            available_memory_bytes=avmem,
            available_gpus=avgpus,
            parallelism=parallelism,
            estimated_tasks=estimate_tasks,
        )

    def probe_async(
        self,
        data_paths: list[str] | None = None,
        estimate_tasks: int = 1,
        parallelism: int = 1,
    ) -> ProbeResult:
        """Async API (calls the sync :meth:`probe` in a thread)."""
        return self.probe(
            data_paths=data_paths,
            estimate_tasks=estimate_tasks,
            parallelism=parallelism,
        )


def apply_probe_result(
    tasks: list[Any],
    probe: ProbeResult,
) -> list[Any]:
    """Adjust task resource allocations based on probe results.

    Args:
        tasks: List of Task objects to adjust.
        probe: ProbeResult with measured infrastructure metrics.

    Returns:
        The same task list (mutated in place) with updated resource allocations.
    """
    suggested_parallelism = probe.suggested_parallelism

    for task in tasks:
        # Adjust CPU based on available vCPUs
        task.resources.cpu = min(task.resources.cpu, probe.available_vcpus)
        task.resources.cpu = max(1, task.resources.cpu)

        # Suggest parallelism for this task
        if suggested_parallelism > 1:
            task.metadata["suggested_parallelism"] = suggested_parallelism

        # Adjust memory if data is large
        if probe.data_size_gb > 1:
            mem_gb = int(task.resources.memory.replace("GB", "").replace("GiB", ""))
            if mem_gb < probe.data_size_gb * 1.5:
                new_mem = max(mem_gb, int(probe.data_size_gb * 1.5))
                task.resources.memory = f"{new_mem}GB"

    return tasks
