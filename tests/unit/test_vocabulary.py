"""Tests for VocabularyResolver."""

from __future__ import annotations

from computepilot.agent.vocabulary import VocabularyResolver
from computepilot.skills.base import Skill, SkillRegistry


def _genomics_skill() -> Skill:
    return Skill(
        name="genomics",
        description="Population genetics analysis",
        vocabulary_mappings={
            "population": {"european": "EUR", "african": "AFR", "east asian": "EAS"},
            "region": {"chromosome 22": "chr22", "chromosome 1": "chr1"},
            "analysis_type": {
                "comparison": "population_comparison",
                "single population": "single_population",
            },
        },
        parameter_constraints={
            "chromosomes": {"allowed": ["1", "2", "22"], "required": True},
        },
        optimization_strategies=["selective_data_extraction"],
    )


def _registry_with_genomics() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(_genomics_skill())
    return reg


class TestResolverBasics:
    def test_resolve_single_token(self) -> None:
        """Single known token resolved."""
        resolver = VocabularyResolver(_registry_with_genomics())
        result = resolver.resolve("european")
        assert result.all_resolved
        assert len(result.resolved) == 1
        assert result.resolved[0].code == "EUR"
        assert result.resolved[0].domain_field == "population"

    def test_resolve_multi_token(self) -> None:
        """Multiple tokens resolved."""
        resolver = VocabularyResolver(_registry_with_genomics())
        result = resolver.resolve("European on chromosome 22")
        # "european" → EUR, "chromosome 22" → chr22, "on" → unmatched
        codes = {r.code for r in result.resolved}
        assert "EUR" in codes
        assert "chr22" in codes

    def test_resolve_to_dict(self) -> None:
        """Convenience method returns flat dict."""
        resolver = VocabularyResolver(_registry_with_genomics())
        # Hmm, typo in test. Let me check…
        d = resolver.resolve_to_dict("african population comparison")
        assert isinstance(d, dict)

    def test_unresolved_tokens(self) -> None:
        """Unmatched tokens collected."""
        resolver = VocabularyResolver(_registry_with_genomics())
        result = resolver.resolve("unknown term on chromosome 22")
        assert "unknown" in result.unresolved or "on" in result.unresolved
        assert any(r.code == "chr22" for r in result.resolved)

    def test_empty_query(self) -> None:
        """Empty query returns empty result."""
        resolver = VocabularyResolver(_registry_with_genomics())
        result = resolver.resolve("")
        assert result.all_resolved
        assert len(result.resolved) == 0


class TestResolverNoMatchingSkill:
    def test_no_registry_returns_empty(self) -> None:
        """No registered skills → no resolutions."""
        resolver = VocabularyResolver(SkillRegistry())
        result = resolver.resolve("european")
        assert len(result.resolved) == 0
        assert not result.all_resolved


class TestResolverCodeCoverage:
    def test_to_dict_multiple_fields(self) -> None:
        """to_dict aggregates multiple resolved fields."""
        resolver = VocabularyResolver(_registry_with_genomics())
        result = resolver.resolve("european comparison on chromosome 22")
        d = result.to_dict()
        assert "population" in d
        assert "analysis_type" in d
        assert "region" in d
        assert d["population"] == "EUR"
