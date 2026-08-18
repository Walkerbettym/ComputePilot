"""LLM provider abstraction — Protocol + OpenAI httpx implementation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    parsed: BaseModel | None = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse: ...

    def structured_output(
        self,
        output_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


_OPENAI_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider:
    """LLM provider backed by OpenAI-compatible API via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        import httpx

        self._api_key = api_key or os.environ.get("SCIFLOW_LLM_API_KEY", "")
        self._base_url = (base_url or os.environ.get("SCIFLOW_LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._model = model or os.environ.get("SCIFLOW_LLM_MODEL", _OPENAI_DEFAULT_MODEL)
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        return self._chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model or self._model,
            temperature=temperature,
        )

    def structured_output(
        self,
        output_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        import json

        schema = output_model.model_json_schema()
        augmented = (
            f"{system_prompt}\n\n"
            f"Your response MUST be valid JSON conforming to this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        raw = self._chat_completion(
            messages=[
                {"role": "system", "content": augmented},
                {"role": "user", "content": user_prompt},
            ],
            model=model or self._model,
            temperature=temperature,
        )
        obj = output_model.model_validate_json(raw.content)
        return LLMResponse(
            content=raw.content,
            parsed=obj,
            model=raw.model,
            usage=raw.usage,
            raw=raw.raw,
        )

    def _chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        resp = self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        choice = data["choices"][0]
        content = choice["message"]["content"] or ""

        usage: dict[str, int] = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            usage=usage,
            raw=data,
        )
