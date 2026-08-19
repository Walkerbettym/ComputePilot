"""SkillRetriever — keyword-based top-k skill retrieval."""

from __future__ import annotations

from computepilot.skills.base import Skill, SkillRegistry


class SkillRetriever:
    """Retrieve matching skills by keyword overlap with name and description."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or SkillRegistry()

    @property
    def registry(self) -> SkillRegistry:
        """Access the underlying registry."""
        return self._registry

    def retrieve(self, query: str, top_k: int = 3) -> list[Skill]:
        """Return top-k skills that best match the query by keyword overlap."""
        if not query.strip():
            return self._registry.list_all()[:top_k]

        query_tokens = set(query.lower().split())
        scored: list[tuple[Skill, int]] = []

        for skill in self._registry.list_all():
            haystack = f"{skill.name} {skill.description}".lower()
            tokens = set(haystack.split())
            score = len(query_tokens & tokens)
            if score > 0 or any(cap in query.lower() for cap in skill.capabilities):
                scored.append((skill, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k]]

    def for_task(self, task_type: str) -> list[Skill]:
        """Return skills whose capabilities match the given task type.

        Maps task type strings (e.g. 'python', 'shell', 'docker', 'slurm')
        to the skill with a matching name.
        """
        skill = self._registry.get(task_type)
        if skill:
            return [skill]
        # Fallback: search by keyword overlap
        return self.retrieve(task_type, top_k=1)

    def for_capability(self, capability: str) -> list[Skill]:
        """Return skills that advertise a specific capability.

        Example: for_capability('run_python') returns the python skill.
        """
        result: list[Skill] = []
        for skill in self._registry.list_all():
            if capability in skill.capabilities:
                result.append(skill)
        return result
