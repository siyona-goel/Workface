"""
WORKFACE — the LLM client.  T3, Day 6, §8 / WORKFACE_TECH_SPEC §10.

    from apps.api.agent.llm import get_client, get_model, is_configured, chat

ONE client, built from three environment variables and NOTHING else:

    LLM_BASE_URL   e.g. http://localhost:11434/v1   (Ollama)
    LLM_API_KEY    any non-empty string             (Ollama ignores the value)
    LLM_MODEL      e.g. qwen3:8b

§10 is decided: WORKFACE runs on OPEN-WEIGHT models behind one env var, because a
contractor's P6 schedule never leaves their network — a procurement unlock, not a
cost saving. Every provider worth using (Ollama, DeepInfra, Together, Groq,
OpenAI, and Gemini's OpenAI-compatible endpoint) speaks the same protocol, so
swapping providers is an ENV CHANGE, never a code change.

    DO NOT add provider branching here. No `if model.startswith(...)`, no
    hardcoded fallback model, no per-provider special-casing. The entire value of
    §10 is that there is none. Setup for each provider is in docs/LLM_SETUP.md;
    do not re-derive it here.

PORTABILITY CAVEAT — read before writing any prompt (docs/LLM_SETUP.md §3):
    Ollama's OpenAI-compatible endpoint DOES NOT support `tool_choice`. A prompt
    that works locally *because it forces a tool call* will behave differently on
    a hosted provider that honours the parameter. So DESIGN EVERY PROMPT TO NEVER
    NEED FORCING — ask for the tool plainly and let the model choose it. This
    module never sends `tool_choice`. (Ollama also ignores `logprobs` and image
    URLs; neither matters here.)

CI: `is_configured()` is False when the env vars are unset, so the smoke test
(tests/test_llm_smoke.py) skips cleanly. There is no key in GitHub Actions and
there must not be one for the test job — CI must never call the model.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

try:  # optional — .env is convenient locally, not required in CI
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass

_ENV_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


class LLMNotConfiguredError(RuntimeError):
    """Raised when a call needs the LLM but the three env vars are not all set."""


def is_configured() -> bool:
    """True only when all three env vars are present and non-empty. The smoke
    test and any optional LLM path gate on this so CI stays model-free."""
    return all(os.environ.get(v) for v in _ENV_VARS)


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        missing = [v for v in _ENV_VARS if not os.environ.get(v)]
        raise LLMNotConfiguredError(
            f"LLM not configured: set {', '.join(missing)} (see docs/LLM_SETUP.md). "
            f"The client is env-var-only; there is no code fallback by design."
        )
    return val


@lru_cache(maxsize=1)
def get_client():
    """The single OpenAI-compatible client. Constructed from LLM_BASE_URL /
    LLM_API_KEY only — no provider branching."""
    from openai import OpenAI  # imported lazily so the package need not be present in CI

    return OpenAI(base_url=_require("LLM_BASE_URL"), api_key=_require("LLM_API_KEY"))


def get_model() -> str:
    return _require("LLM_MODEL")


def chat(messages: list[dict[str, Any]], tools: list[dict] | None = None,
         **kwargs: Any):
    """One chat completion against the configured model. NEVER passes
    `tool_choice` (Ollama does not support it, §10 portability). Extra kwargs are
    forwarded, but do not add `tool_choice` here or in callers."""
    kwargs.pop("tool_choice", None)   # belt-and-braces: never force a tool
    return get_client().chat.completions.create(
        model=get_model(), messages=messages, tools=tools, **kwargs
    )


__all__ = ["LLMNotConfiguredError", "is_configured", "get_client", "get_model", "chat"]
