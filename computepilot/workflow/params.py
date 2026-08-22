"""Workflow parameter substitution — ``${key}`` / ``${key:-default}`` placeholders."""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class MissingParameterError(ValueError):
    """Raised when required ``${key}`` placeholders have no value."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"missing required parameter(s): {', '.join(missing)}")


def substitute(value: str, params: dict[str, str]) -> str:
    """Replace placeholders in *value*; raise on missing keys without defaults."""

    def _sub(match: re.Match[str]) -> str:
        key, default = match.group(1), match.group(2)
        if key in params:
            return params[key]
        if default is not None:
            return default
        raise MissingParameterError([key])

    return _PLACEHOLDER.sub(_sub, value)


def substitute_partial(value: str, params: dict[str, str]) -> str:
    """Replace known ``${key}`` occurrences; leave unknown placeholders intact."""

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        if key in params:
            return params[key]
        if default is not None:
            return default
        return match.group(0)

    return _PLACEHOLDER.sub(_sub, value)


def _walk(obj: Any, params: dict[str, str], missing: set[str]) -> Any:
    if isinstance(obj, str):
        try:
            return substitute(obj, params)
        except MissingParameterError as exc:
            missing.update(exc.missing)
            return obj
    if isinstance(obj, list):
        return [_walk(item, params, missing) for item in obj]
    if isinstance(obj, dict):
        return {k: _walk(v, params, missing) for k, v in obj.items()}
    return obj


def substitute_workflow_data(data: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    """Recursively substitute parameters in raw workflow YAML data.

    Collects *all* missing keys before raising, so the user sees the full
    list in one round-trip.
    """
    missing: set[str] = set()
    result = _walk(data, params, missing)
    if missing:
        raise MissingParameterError(sorted(missing))
    return result  # type: ignore[no-any-return]


def parse_set_args(pairs: list[str] | None) -> dict[str, str]:
    """Parse ``--set key=value`` CLI arguments into a dict."""
    result: dict[str, str] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"invalid --set argument (expected key=value): {pair!r}")
        result[key.strip()] = value
    return result
