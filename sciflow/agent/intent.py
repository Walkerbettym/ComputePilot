"""Intent extraction — structured intent from natural language."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sciflow.agent.provider import LLMProvider


class Intent(BaseModel):
    """Structured representation of a user's intent for a workflow."""

    verb: str = Field(description="Primary action: run, train, evaluate, preprocess, simulate, ...")
    target: str = Field(description="What to act on: model name, dataset, script, experiment, ...")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Key parameters extracted from the request",
    )
    resources: dict[str, Any] = Field(
        default_factory=lambda: {"cpu": 1, "memory": "2GB", "gpu": 0},
        description="Resource requirements inferred from the request",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints: time limits, accuracy thresholds, budget, ...",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made during extraction",
    )


_SYSTEM_PROMPT = (
    """\
You are a scientific workflow intent extractor. Given a user's natural language request,
extract structured intent as a JSON object conforming to the schema below.

The fields are:
"""
    "- verb: The primary action (e.g., \"run\", \"train\", \"evaluate\", \"preprocess\", "
    '"simulate", "benchmark").\n'
    "- target: The thing the action applies to (e.g., model name, dataset, "
    "script path, experiment name).\n"
    "- parameters: A dict of key-value pairs for important parameters "
    "(e.g., learning rate, epochs, batch size, input files).\n"
    "- resources: A dict with cpu (int), memory (str like \"2GB\"), gpu (int) "
    "- infer from the request or use defaults.\n"
    "- constraints: A list of explicit constraints "
    "(time limits, accuracy requirements, budget limits, etc.).\n"
    "- assumptions: A list of assumptions you made during extraction "
    '(e.g., "assumed Python 3.11", "assumed GPU not needed").\n'
    "\n"
    "Be precise. Extract only what the user explicitly states or clearly "
    "implies. Do not hallucinate parameters."
)


class IntentExtractor:
    """Extract structured Intent from natural language using an LLM provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def extract(self, query: str, *, model: str | None = None) -> Intent:
        """Extract an Intent from a free-form user query."""
        response = self._provider.structured_output(
            Intent,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=query,
            model=model,
        )
        assert isinstance(response.parsed, Intent)
        return response.parsed
