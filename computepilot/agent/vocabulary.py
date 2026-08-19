"""VocabularyResolver — resolve natural-language tokens to domain codes using Skills.

This implements the paper's vocabulary-mapping function of the knowledge layer.
The resolver consults all registered Skills' ``vocabulary_mappings`` to translate
natural-language terms (e.g. "european", "chromosome 22") into canonical domain
codes (e.g. "EUR", "chr22").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from computepilot.skills.base import Skill, SkillRegistry


@dataclass
class ResolvedToken:
    """Result of resolving a single token against a skill."""

    token: str
    skill_name: str
    domain_field: str
    code: str


@dataclass
class ResolutionResult:
    """Aggregated result of resolving a natural-language query."""

    resolved: list[ResolvedToken] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def all_resolved(self) -> bool:
        """True when every candidate token was resolved."""
        return len(self.unresolved) == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict of field → code mappings."""
        return {r.domain_field: r.code for r in self.resolved}


class VocabularyResolver:
    """Resolve natural-language tokens to domain codes via Skills.

    Usage::

        resolver = VocabularyResolver(registry)
        result = resolver.resolve("European population on chromosome 22")
        # → multiple ResolvedToken objects
        #     ResolvedToken('chromosome 22', 'genomics', 'region', 'chr22')]
    """

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or SkillRegistry()
        self._token_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9_ ]*[a-zA-Z0-9]|[a-zA-Z0-9]")

    def resolve(self, query: str, skill_name: str | None = None) -> ResolutionResult:
        """Tokenize *query* and resolve each token against Skill vocabulary.

        If *skill_name* is given, only that skill is consulted.
        Otherwise all registered skills are tried.
        """
        result = ResolutionResult()
        tokens = self._tokenize(query)

        for token in tokens:
            resolved = self._resolve_single(token, skill_name)
            if resolved is not None:
                result.resolved.append(resolved)
            else:
                result.unresolved.append(token)

        return result

    def resolve_to_dict(self, query: str, skill_name: str | None = None) -> dict[str, str]:
        """Convenience: resolve and return a flat field → code dict."""
        return self.resolve(query, skill_name=skill_name).to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokenize(self, query: str) -> list[str]:
        """Split *query* into candidate tokens for resolution."""
        raw = query.lower().strip()
        if not raw:
            return []

        tokens: list[str] = []
        # Try multi-word n-grams first (e.g. "chromosome 22")
        words = raw.split()
        for size in range(min(4, len(words)), 0, -1):
            i = 0
            while i + size <= len(words):
                ngram = " ".join(words[i : i + size])
                if ngram not in tokens:
                    tokens.append(ngram)
                i += 1
        return tokens

    def _resolve_single(self, token: str, skill_name: str | None = None) -> ResolvedToken | None:
        """Try to resolve *token* against skills."""
        skills: list[Skill] = []
        if skill_name:
            skill = self._registry.get(skill_name)
            if skill:
                skills = [skill]
        else:
            skills = self._registry.list_all()

        for skill in skills:
            for voc_field in skill.vocabulary_mappings:
                code = skill.resolve_vocabulary(token, field=voc_field)
                if code is not None:
                    return ResolvedToken(
                        token=token,
                        skill_name=skill.name,
                        domain_field=voc_field,
                        code=code,
                    )
        return None
