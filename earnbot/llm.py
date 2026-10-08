"""Claude via the Claude Code CLI, billed to a Claude Pro/Max subscription (no API key)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class JSONModel(Protocol):
    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


# An API key in the environment would take precedence over the subscription login,
# so it is stripped before every call: all usage goes to the Max plan.
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def has_credentials() -> bool:
    """True when the `claude` CLI is installed and can authenticate with the subscription.

    In CI that means CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`); on your own
    machine a normal `claude` login is enough.
    """
    if shutil.which("claude") is None:
        return False
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) or not os.environ.get("CI")


class ClaudeCodeJSON:
    """Runs `claude -p` headless with a JSON schema and returns the validated object."""

    def __init__(self, model: str, effort: str, timeout: int = 1800, binary: str = "claude",
                 retry_waits: tuple[int, ...] = (60, 180)):
        self.retry_waits = retry_waits
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.binary = binary

    def command(self, system: str, schema: dict[str, Any]) -> list[str]:
        return [
            self.binary, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system,
            "--model", self.model,
            "--effort", self.effort,
            "--tools", "",               # pure writing: no file/shell/web tools
            "--max-turns", "5",
            "--no-session-persistence",
        ]

    def generate_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        # Retry transient failures (rate limits, overload, timeouts) with backoff before giving up.
        for wait in self.retry_waits:
            try:
                return self._once(system, prompt, schema)
            except LLMError:
                time.sleep(wait)
        return self._once(system, prompt, schema)

    def _once(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        env = {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}
        try:
            proc = subprocess.run(
                self.command(system, schema), input=prompt, env=env,
                capture_output=True, text=True, timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise LLMError("`claude` CLI not found: npm install -g @anthropic-ai/claude-code") from e
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude timed out after {self.timeout}s") from e

        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            detail = (proc.stderr or proc.stdout).strip()[-500:]
            raise LLMError(f"claude exited {proc.returncode}: {detail}") from None

        if result.get("is_error") or result.get("subtype") != "success":
            raise LLMError(f"claude failed ({result.get('subtype')}): {str(result.get('result'))[:500]}")
        data = result.get("structured_output")
        if not isinstance(data, dict):
            raise LLMError("claude returned no structured output")
        return data
