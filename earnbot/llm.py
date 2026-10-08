"""Thin Claude client that returns schema-validated JSON."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import anthropic


class LLMError(RuntimeError):
    pass


class JSONModel(Protocol):
    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class ClaudeJSON:
    """Calls Claude with structured outputs so every response parses as the given schema."""

    def __init__(self, model: str, effort: str, client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            # Streaming keeps long article generations clear of HTTP timeouts.
            # Server-side fallbacks re-run a policy-declined request on a fallback model.
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=system,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = stream.get_final_message()
        except anthropic.RateLimitError as e:
            raise LLMError(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e

        if message.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if message.stop_reason == "max_tokens":
            raise LLMError("response truncated at max_tokens")
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise LLMError("no text block in response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from model: {e}") from e
