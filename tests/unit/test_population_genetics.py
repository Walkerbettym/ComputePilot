"""Integration test: population_genetics skill full pipeline."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from computepilot.agent.conductor import Conductor
from computepilot.agent.vocabulary import VocabularyResolver
from computepilot.models.run import Run, TaskStatus
from computepilot.runtime.probe import EnvironmentProbe
from computepilot.runtime.sentinel import ExecutionSentinel
from computepilot.runtime.state import StateStore
from computepilot.skills.base import SkillRegistry
from computepilot.skills.population_genetics import population_genetics_skill
from tests.unit.test_conductor import MockProvider


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(population_genetics_skill)
    return reg


class TestVocabulary:
    def test_resolve_population(self, registry: SkillRegistry) -> None:
        resolver = VocabularyResolver(registry)
        result = resolver.resolve("european")
        codes = [r.code for r in result.resolved]
        assert "EUR" in codes

    def test_resolve_chromosome(self, registry: SkillRegistry) -> None:
        resolver = VocabularyResolver(registry)
        result = resolver.resolve("chromosome 22")
        codes = [r.code for r in result.resolved]
        assert "chr22" in codes

    def test_resolve_full_query(self, registry: SkillRegistry) -> None:
        resolver = VocabularyResolver(registry)
        result = resolver.resolve(
            "population comparison between European and African on chromosome 22"
        )
        codes = {r.code for r in result.resolved}
        assert "EUR" in codes
        assert "AFR" in codes
        assert "chr22" in codes


class TestConductor:
    def test_route_to_genetics(self, registry: SkillRegistry) -> None:
        cond = Conductor(provider=MockProvider(), registry=registry)
        sid = cond.new_session()
        _ = cond.turn_sync(sid, "european comparison on chromosome 22")
        session = cond.get_session(sid)
        assert session is not None
        assert session.selected_skill is not None
        assert session.selected_skill.name == "population_genetics"

    def test_clarification(self, registry: SkillRegistry) -> None:
        cond = Conductor(provider=MockProvider(), registry=registry)
        sid = cond.new_session()
        r1 = cond.turn_sync(sid, "european")
        assert r1.requires_clarification
        r2 = cond.turn_sync(sid, "comparison")
        assert not r2.requires_clarification

    def test_approval(self, registry: SkillRegistry) -> None:
        cond = Conductor(provider=MockProvider(), registry=registry)
        sid = cond.new_session()
        r1 = cond.turn_sync(sid, "european comparison")
        if r1.requires_clarification:
            r1 = cond.turn_sync(sid, "comparison")
        if r1.phase == "approval":
            final = cond.turn_sync(sid, "yes")
            assert final.phase == "done"
        session = cond.get_session(sid)
        assert session is not None


class TestProbe:
    def test_probe_with_data(self, tmp_path: Path) -> None:
        data = tmp_path / "sample.vcf"
        data.write_text("line\n" * 1000)
        probe = EnvironmentProbe()
        result = probe.probe(data_paths=[str(data)], estimate_tasks=10)
        assert result.data_size_bytes > 0
        assert result.estimated_tasks == 10


class TestSentinel:
    @pytest.mark.asyncio
    async def test_sentinel_monitors(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "g.db")
        store.create_run(Run(id="r", workflow_id=uuid4(), workflow_sha256="abc"))
        store.transition_task("r", "fetch", TaskStatus.SUCCEEDED)
        store.transition_task("r", "call", TaskStatus.RUNNING)
        sent = ExecutionSentinel(state=store)
        sent.watch("r", total_tasks=5)
        report = sent.report_progress("r")
        assert report is not None
        assert report.total_tasks == 5
        assert report.completed >= 1
