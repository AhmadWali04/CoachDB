"""Schema-constrained LLM calls for the coach agents.

Coaches depend on the `StructuredLLM` protocol, not on a provider, so tests
use a fake and the model can be swapped. `ClaudeStructuredLLM` asks Claude for
JSON matching a Pydantic model (structured outputs), validates it, and on a
validation problem sends one bounded correction turn (PRD §6.2). Callers
decide what to do if it still fails (the coaches fall back to safe defaults).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
# Opus 5.5 can decline a request; "default" re-runs it on Anthropic's
# recommended fallback model server-side instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Keywords structured outputs don't accept; Pydantic still enforces them.
_UNSUPPORTED = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "default",
}


class LLMUnavailable(RuntimeError):
    """The model could not produce a usable answer (error, refusal, or invalid twice)."""


Checker = Callable[[BaseModel], list[str]]


class StructuredLLM(Protocol):
    def complete[M: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        output: type[M],
        effort: str,
        check: Checker | None = None,
    ) -> M:
        """Return a validated `output`; `check` adds domain errors (e.g. bad evidence IDs)."""
        ...


def wire_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema reduced to what structured outputs accept."""

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            out = {k: clean(v) for k, v in node.items() if k not in _UNSUPPORTED}
            if out.get("type") == "object" or "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out.get("properties", {}))
            return out
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(model.model_json_schema())


@dataclass
class ClaudeStructuredLLM:
    client: Any = None  # anthropic.Anthropic; created lazily so tests never need it
    model: str = DEFAULT_MODEL
    max_tokens: int = 16000
    timeout_s: float = 120.0
    max_retries: int = 2

    def _client(self) -> Any:
        if self.client is None:
            import anthropic

            # Zero-arg client: ANTHROPIC_API_KEY, or an `ant auth login` profile.
            self.client = anthropic.Anthropic(timeout=self.timeout_s, max_retries=self.max_retries)
        return self.client

    def complete[M: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        output: type[M],
        effort: str,
        check: Checker | None = None,
    ) -> M:
        import anthropic

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        schema = wire_schema(output)
        for attempt in (1, 2):
            try:
                response = self._client().beta.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=messages,
                    thinking={"type": "adaptive"},
                    output_config={
                        "effort": effort,
                        "format": {"type": "json_schema", "schema": schema},
                    },
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                )
            except anthropic.APIStatusError as exc:
                raise LLMUnavailable(f"API error {exc.status_code}") from exc
            except anthropic.APIConnectionError as exc:  # includes timeouts
                raise LLMUnavailable("could not reach the model") from exc

            if response.stop_reason == "refusal":
                raise LLMUnavailable("model declined the request")
            if response.stop_reason == "max_tokens":
                raise LLMUnavailable("response hit max_tokens")
            text = next((b.text for b in response.content if b.type == "text"), "")
            errors = _validate(text, output, check)
            if isinstance(errors, BaseModel):
                return errors
            logger.warning(
                "coach output invalid", extra={"attempt": attempt, "errors": len(errors)}
            )
            if attempt == 2:
                break
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": correction_prompt(errors)},
            ]
        raise LLMUnavailable("output still invalid after one correction")


def _validate[M: BaseModel](text: str, output: type[M], check: Checker | None) -> M | list[str]:
    try:
        parsed = output.model_validate(json.loads(text))
    except json.JSONDecodeError:
        return ["Response was not valid JSON."]
    except ValidationError as exc:
        return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()][:20]
    problems = check(parsed) if check else []
    return problems or parsed


def correction_prompt(errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    return (
        "Your previous answer did not pass validation:\n"
        f"{listed}\n"
        "Return the full corrected JSON. Only cite evidence IDs that appear in the match data."
    )
