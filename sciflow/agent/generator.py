"""Workflow generator — orchestrates intent extraction and planning."""

from __future__ import annotations

from sciflow.agent.intent import Intent, IntentExtractor
from sciflow.agent.planner import Planner
from sciflow.agent.provider import LLMProvider
from sciflow.models.workflow import Workflow


class WorkflowGenerator:
    """High-level workflow generator that extracts intent and plans a workflow."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        extractor: IntentExtractor | None = None,
        planner: Planner | None = None,
    ) -> None:
        self._extractor = extractor or IntentExtractor(provider)
        self._planner = planner or Planner()

    def generate(self, query: str, *, model: str | None = None) -> Workflow:
        """Extract intent from a query and generate a workflow."""
        intent = self._extractor.extract(query, model=model)
        return self._planner.plan(intent)

    def extract_intent(self, query: str, *, model: str | None = None) -> Intent:
        """Extract intent only, without planning."""
        return self._extractor.extract(query, model=model)
