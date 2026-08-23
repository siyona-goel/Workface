"""
WORKFACE — LLM smoke test.  T3, Day 6, §8.

ONE test: the configured model responds and can return a tool call. Not ten
scenarios — tests/test_agent_replay.py (the ten-scenario, both-models replay) is
Day-7 work.

It SKIPS cleanly when the LLM is not configured, so CI (which has no key and must
never call a model) stays green. Run it locally after pointing .env at your model
(docs/LLM_SETUP.md):

    Ollama:  LLM_BASE_URL=http://localhost:11434/v1  LLM_API_KEY=ollama  LLM_MODEL=qwen3:8b
    Gemini:  LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
             LLM_API_KEY=<key>  LLM_MODEL=gemini-2.0-flash

NB: no `tool_choice` is sent (Ollama does not support it). The prompt asks for the
tool plainly and lets the model choose it — the portability discipline from §10.
"""

from __future__ import annotations

import pytest

from apps.api.agent import llm

pytestmark = pytest.mark.skipif(
    not llm.is_configured(),
    reason="LLM not configured (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL unset) — skipping; CI stays model-free",
)

# A minimal WORKFACE-flavoured tool. The prompt below invites it plainly so no
# forcing (tool_choice) is needed — the same shape the agent loop will use.
_FLAG_TOOL = [{
    "type": "function",
    "function": {
        "name": "flag_activity",
        "description": "Flag a scheduled construction activity as thermally at-risk.",
        "parameters": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "string", "description": "e.g. A-2009"},
                "reason": {"type": "string", "description": "Short reason."},
            },
            "required": ["activity_id", "reason"],
        },
    },
}]


def test_model_responds():
    """The configured model returns a chat completion at all."""
    resp = llm.chat(
        messages=[{"role": "user", "content": "Reply with the single word: ready."}],
        max_tokens=16,
    )
    assert resp.choices, "no choices returned"
    # Some models put content on message.content; just assert the call succeeded.
    assert resp.choices[0].message is not None


def test_model_can_return_a_tool_call():
    """The model can emit a correct tool call WITHOUT tool_choice forcing."""
    resp = llm.chat(
        messages=[
            {"role": "system",
             "content": "You are a scheduling agent. When an activity is at risk, call the "
                        "flag_activity tool with its id and a one-line reason. Use the tool."},
            {"role": "user",
             "content": "Activity A-2009 (epoxy coating on the FAB2 deck) is at risk because the "
                        "surface will fall below the dew-point offset at dawn. Flag it."},
        ],
        tools=_FLAG_TOOL,
        max_tokens=256,
    )
    msg = resp.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None)
    assert tool_calls, f"expected a tool call; got content: {getattr(msg, 'content', None)!r}"
    call = tool_calls[0]
    assert call.function.name == "flag_activity"
    import json
    args = json.loads(call.function.arguments)
    assert "activity_id" in args and "reason" in args
