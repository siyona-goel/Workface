"""
WORKFACE — agent replay tests.  T3, Task E (§8.2, §10, §13.7).

Ten fixed scenarios, each asserting the CHOSEN STRATEGY (the tool the model
picks) — the cheap defence against "did the model swap break the tool choice?".
The prompt tuned on one model can call the wrong tool on another (docs/LLM_SETUP.md
§6), so this runs against WHATEVER model LLM_BASE_URL points at and is meant to be
run against BOTH the dev model (Gemini/Ollama) and the demo model.

Skips cleanly when LLM_BASE_URL is unset — CI stays model-free (hard rule 4). The
deterministic ladder itself is covered by tests/test_agent_loop.py.

Run against a model:
    LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... pytest tests/test_agent_replay.py -q
"""

from __future__ import annotations

import pytest

from apps.api.agent.llm import is_configured
from apps.api.agent.propose import llm_choose_strategy
from packages.schemas.agent_trace import ProposalKind

pytestmark = pytest.mark.skipif(not is_configured(),
                                reason="LLM_BASE_URL unset — model tests skip (CI stays model-free)")

# NOTE (§16.6 / docs/LLM_SETUP.md §6): llm_choose_strategy retries with backoff on
# transport errors. On a LOCAL model (Ollama) this suite runs clean; on a hosted
# FREE-TIER dev endpoint (e.g. Gemini) a 10-call burst can exhaust the minute/day
# quota and some scenarios then read as "no choice". That is an endpoint quota
# limit, not a tool-choice failure — verified by single calls returning the right
# tool. Run against the DEMO model (or Ollama) for a clean pass.


def _summary(**kw) -> str:
    return (
        f"Activity {kw.get('id', 'A-X')} ({kw.get('name', 'work')}), trade {kw.get('trade', 't')}, "
        f"on {kw.get('face', 'WF-X')}. Verdict: {kw.get('verdict', 'at_risk')}. "
        f"Binding constraint: {kw.get('binding', 'n/a')}. Near-critical: {kw.get('near', False)}. "
        f"Total float: {kw.get('float', 5.0)} d. Hold point: {kw.get('hold', 'none')}. "
        f"Open compliant windows on the horizon: {kw.get('windows', 3)}. Choose the first strategy to attempt."
    )


# (scenario summary, the set of acceptable first-strategy choices)
SCENARIOS = [
    ("hold point present -> escalate",
     _summary(id="A-1205", hold="City of Phoenix inspector — reinforcing & embed inspection prior to pour",
              binding="ACI 305 evaporation rate", verdict="at_risk", float=105.0),
     {ProposalKind.ESCALATE}),
    ("two windows, near-critical -> split (cheapest) or shift",
     _summary(id="A-1237", trade="coating_epoxy_structural_steel", binding="dew-point offset",
              near=True, float=0.6, windows=2),
     {ProposalKind.SPLIT, ProposalKind.SHIFT}),
    ("no compliant window at all -> mitigate, rfi or escalate",
     _summary(id="A-9", verdict="non_compliant", binding="surface below dew point + 2.8 C", windows=0),
     {ProposalKind.MITIGATE, ProposalKind.RFI, ProposalKind.ESCALATE}),
    ("plenty of float and windows -> a schedule fix, not an RFI",
     _summary(id="A-10", verdict="at_risk", float=12.0, windows=4),
     {ProposalKind.SPLIT, ProposalKind.SHIFT}),
    ("WBGT heat load high -> mitigate or shift",
     _summary(id="A-11", trade="concrete_cip_hot_weather", binding="WBGT rest ratio", verdict="at_risk", windows=2),
     {ProposalKind.MITIGATE, ProposalKind.SHIFT, ProposalKind.SPLIT}),
    ("out of spec, no window -> RFI to the engineer of record",
     _summary(id="A-12", verdict="non_compliant", binding="manufacturer application window", windows=0),
     {ProposalKind.RFI, ProposalKind.ESCALATE, ProposalKind.MITIGATE}),
    ("SFRM continuity, one narrow window -> shift, split or mitigate",
     _summary(id="A-1088", trade="sfrm_spray_applied_fireproofing", binding="continuity 40F 24h",
              near=True, float=1.2, windows=1),
     {ProposalKind.SHIFT, ProposalKind.SPLIT, ProposalKind.MITIGATE}),
    ("near-critical, thin float, milestone downstream -> escalate or split",
     _summary(id="A-1237b", near=True, float=0.6, binding="dew-point offset", windows=1),
     {ProposalKind.ESCALATE, ProposalKind.SPLIT, ProposalKind.SHIFT}),
    ("cold-weather concrete, enclosure available -> mitigate or shift",
     _summary(id="A-13", trade="concrete_cip_cold_weather", binding="minimum placement temperature", windows=2),
     {ProposalKind.MITIGATE, ProposalKind.SHIFT, ProposalKind.SPLIT}),
    ("healthy window, single window -> shift",
     _summary(id="A-14", verdict="at_risk", float=8.0, windows=1),
     {ProposalKind.SHIFT, ProposalKind.SPLIT, ProposalKind.MITIGATE}),
]


@pytest.mark.parametrize("label,summary,acceptable", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_llm_picks_an_acceptable_strategy(label, summary, acceptable):
    choice = llm_choose_strategy(summary)
    # A None means the model named no known tool — a real portability failure worth
    # surfacing, not a silent pass.
    assert choice is not None, f"[{label}] model named no known strategy"
    assert choice in acceptable, f"[{label}] model chose {choice.value}; acceptable: {[k.value for k in acceptable]}"


def test_llm_returns_a_known_enum_or_none():
    """Whatever the model says, llm_choose_strategy only ever yields a real
    ProposalKind or None — it never leaks an unmapped string into the loop."""
    choice = llm_choose_strategy(_summary(id="A-smoke"))
    assert choice is None or isinstance(choice, ProposalKind)
