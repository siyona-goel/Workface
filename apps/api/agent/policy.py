"""
WORKFACE — the policy gate.  T3, Day 7, Task C (§4.3, §8.3).

    from apps.api.agent.policy import evaluate_policy, GateContext, load_policy

THE AGENT PROPOSES; THIS CODE DISPOSES (hard rule 2). Pure Python reading one
YAML file (config/policy.yaml). A model cannot approve its own proposal, cannot
edit the policy, and cannot see the gate's internals. Every gated tool routes
through `evaluate_policy` before it executes — no exceptions, no "just this once".

Each rule is a pure function `(ctx, cfg) -> GateVerdict | None`; None means the
rule did not fire. `evaluate_policy` runs them in priority order (the most
contractual / safety-critical first) and returns the FIRST non-approve verdict,
or an approve verdict if every rule passes. The reason on every verdict NAMES the
rule's basis — the number and the requirement, not "policy denied" (§7).

Rule ids are a contract with T1's escalation UI (§2.6). `split_within_float_ok`
and `max_float_days_consumed` MUST keep those exact names.

CI has no model: the gate never calls the LLM. Tests build the Proposal / context
objects directly (hard rule 4).

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from packages.schemas.agent_trace import (
    GateDecision,
    GateVerdict,
    Proposal,
    ProposalKind,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_YAML = _REPO_ROOT / "config" / "policy.yaml"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PolicyConfig:
    max_float_days_consumed: float = 3.0
    max_float_fraction_consumed: float = 1.0
    wbgt_min_work_fraction: float = 0.5
    forecast_max_age_h: float = 2.0
    night_start_hour: int = 19
    night_end_hour: int = 5
    guard_milestones: bool = True
    guard_precedence: bool = True
    guard_hold_points: bool = True
    guard_out_of_spec: bool = True


@lru_cache(maxsize=1)
def load_policy(path: str | None = None) -> PolicyConfig:
    import yaml
    p = Path(path) if path else POLICY_YAML
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    fields = PolicyConfig.__dataclass_fields__
    return PolicyConfig(**{k: raw[k] for k in fields if k in raw})


# --------------------------------------------------------------------------- #
# Context the rules read. The loop assembles this from the pack result + the
# activity data; tests construct it directly (no model needed).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MilestoneRisk:
    activity_id: str
    milestone_name: str
    milestone_date: datetime
    projected_date: datetime            # where the proposal would push this activity's finish

    @property
    def breached(self) -> bool:
        return self.projected_date > self.milestone_date


@dataclass(frozen=True)
class GateContext:
    """Everything the eight rules need. Field defaults are the benign case, so a
    test sets only what its rule cares about."""
    kind: ProposalKind
    activity_ids: list[str]

    # float
    is_near_critical: bool = False
    float_days_consumed: float = 0.0        # from the proposal (also on Proposal.float_days_consumed)
    activity_total_float_d: float | None = None   # the activity's OWN float, for the fractional cap

    # milestones downstream of the move
    milestones: list[MilestoneRisk] = field(default_factory=list)

    # precedence
    breaks_precedence: bool = False
    precedence_detail: str = ""

    # hold point on any affected activity
    hold_point: str | None = None

    # manufacturer window
    out_of_spec: bool = False
    out_of_spec_detail: str = ""

    # night work — the placement's start hour, site-local
    placement_start: datetime | None = None

    # crew heat load — min WBGT work_fraction across the placement (1.0 = full work)
    wbgt_work_fraction: float | None = None

    # forecast freshness — age of the evaluated series in hours; None = missing
    forecast_age_h: float | None = None


# --------------------------------------------------------------------------- #
# Verdict helpers
# --------------------------------------------------------------------------- #

def _deny(rule_id: str, reason: str) -> GateVerdict:
    return GateVerdict(decision=GateDecision.DENY, rule_id=rule_id, reason=reason[:500], escalated=True)


def _approve(rule_id: str, reason: str) -> GateVerdict:
    return GateVerdict(decision=GateDecision.APPROVE, rule_id=rule_id, reason=reason[:500], escalated=False)


# --------------------------------------------------------------------------- #
# The eight rules (§4.3). Each returns a deny GateVerdict when it fires, else None.
# --------------------------------------------------------------------------- #

def fail_closed_on_stale_forecast(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Series older than the cap, or missing — escalate, never guess."""
    age = ctx.forecast_age_h
    if age is None:
        return _deny("fail_closed_on_stale_forecast",
                     "Denied: no forecast series backs this placement — fail closed, never guess. "
                     "Escalating for a fresh evaluation before any crew is committed.")
    if age > cfg.forecast_max_age_h:
        return _deny("fail_closed_on_stale_forecast",
                     f"Denied: the thermal series is {age:.1f} h old, past the {cfg.forecast_max_age_h:g} h "
                     f"freshness limit. A stale forecast is not a basis to move a crew — escalating for a refresh.")
    return None


def no_precedence_violation(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Never break an FS link — no coating a substrate that has not cured."""
    if cfg.guard_precedence and ctx.breaks_precedence:
        detail = ctx.precedence_detail or "an FS predecessor would not be finished in time"
        return _deny("no_precedence_violation",
                     f"Denied: the move breaks a finish-to-start link — {detail}. "
                     f"You cannot coat a substrate that has not cured. Escalating.")
    return None


def no_move_inspection_hold_point(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """An activity carrying an inspection hold point is not the agent's to move."""
    if cfg.guard_hold_points and ctx.hold_point:
        return _deny("no_move_inspection_hold_point",
                     f"Denied: this activity carries an inspection hold point — \"{ctx.hold_point}\". "
                     f"An inspection gate is a human coordination, not a resequencing the agent can make. Escalating.")
    return None


def no_move_past_milestone(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Never push any activity past a contractual milestone date."""
    if not cfg.guard_milestones:
        return None
    breached = [m for m in ctx.milestones if m.breached]
    if breached:
        m = max(breached, key=lambda x: x.projected_date - x.milestone_date)
        over_h = (m.projected_date - m.milestone_date).total_seconds() / 3600.0
        return _deny("no_move_past_milestone",
                     f"Denied: the move pushes {m.activity_id} past {m.milestone_name} "
                     f"({m.milestone_date:%d %b %H:%M}) by ~{over_h:.0f} h — a contractual milestone "
                     f"the contractor cannot slip. Escalating with the tradeoff.")
    return None


def no_out_of_spec_application(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Application outside a manufacturer's published window — RFI ONLY, never
    auto-approve. Only the engineer of record may accept out-of-spec work."""
    if cfg.guard_out_of_spec and ctx.out_of_spec and ctx.kind is not ProposalKind.RFI:
        detail = ctx.out_of_spec_detail or "the placement sits outside the manufacturer's published window"
        return _deny("no_out_of_spec_application",
                     f"Denied: {detail}. Applying outside the published window voids the warranty; only the "
                     f"engineer of record can accept it, via RFI. Escalating — this is never auto-approved.")
    return None


def max_float_days_consumed(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Float spend over the cap on a near-critical activity. TWO thresholds (§6.1):
    the absolute day cap AND the fractional cap. Reports which one fired."""
    if not ctx.is_near_critical:
        return None
    spent = ctx.float_days_consumed
    own = ctx.activity_total_float_d
    frac = (spent / own) if (own and own > 0) else None

    over_abs = spent > cfg.max_float_days_consumed + 1e-9
    # `>=` so that spending the ENTIRE float (100%) trips the rule — the knife-edge
    # §6.1 exists to catch. cap=1.0 therefore means "may not consume the whole float".
    over_frac = frac is not None and frac >= cfg.max_float_fraction_consumed - 1e-9
    if not (over_abs or over_frac):
        return None

    if over_frac and not over_abs:
        return _deny("max_float_days_consumed",
                     f"Denied: this near-critical activity has only {own:g} d of float and the move spends "
                     f"{spent:g} d — {frac:.0%} of it, over the {cfg.max_float_fraction_consumed:.0%} cap. "
                     f"An absolute-days cap would never catch a float this thin. Escalating.")
    basis = f"the {cfg.max_float_days_consumed:g} d cap"
    if over_frac:
        basis += f" and {cfg.max_float_fraction_consumed:.0%} of its {own:g} d float"
    return _deny("max_float_days_consumed",
                 f"Denied: the move spends {spent:g} d of float on a near-critical activity, over {basis}. "
                 f"No compliant sequence preserves it — escalating to the superintendent with the tradeoff.")


def no_auto_night_work(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Night work is never auto-approved — lighting, noise ordinance and a second
    shift are human decisions."""
    st = ctx.placement_start
    if st is None:
        return None
    h = st.hour
    is_night = h >= cfg.night_start_hour or h < cfg.night_end_hour
    if is_night:
        return _deny("no_auto_night_work",
                     f"Denied: the placement starts at {st:%H:%M}, inside the "
                     f"{cfg.night_start_hour:02d}:00–{cfg.night_end_hour:02d}:00 night window. Night work needs a "
                     f"lighting plan, noise-ordinance clearance and a second-shift crew — human calls. Escalating.")
    return None


def wbgt_rest_ratio_escalate(ctx: GateContext, cfg: PolicyConfig) -> GateVerdict | None:
    """Crew would work a band requiring > 50% rest (work_fraction below the floor)."""
    wf = ctx.wbgt_work_fraction
    if wf is not None and wf + 1e-9 < cfg.wbgt_min_work_fraction:
        rest = 1.0 - wf
        return _deny("wbgt_rest_ratio_escalate",
                     f"Denied: the placement puts the crew in a WBGT band at {wf:.0%} work / {rest:.0%} rest, "
                     f"past the 50% rest line the OSHA heat trigger flags. Committing a crew to that heat load "
                     f"is a supervisor's call — escalating.")
    return None


# Priority order: fail-closed first, then the contractual / safety hard stops,
# then float, then the human-decision escalations.
_RULES = (
    fail_closed_on_stale_forecast,
    no_precedence_violation,
    no_move_inspection_hold_point,
    no_move_past_milestone,
    no_out_of_spec_application,
    max_float_days_consumed,
    no_auto_night_work,
    wbgt_rest_ratio_escalate,
)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def evaluate_policy(proposal: Proposal, ctx: GateContext,
                    cfg: PolicyConfig | None = None) -> GateVerdict:
    """Run every rule in priority order. Return the first deny; else approve.

    The approve verdict's rule_id is `split_within_float_ok` for a split (the id
    T1's UI already uses) and a generic approve id otherwise. The reason names
    the float actually spent so an approve is as auditable as a deny."""
    cfg = cfg or load_policy()
    for rule in _RULES:
        verdict = rule(ctx, cfg)
        if verdict is not None:
            return verdict

    # Nothing fired — approve.
    spent = ctx.float_days_consumed
    own = ctx.activity_total_float_d
    within = (f"consumes {spent:g} d of float"
              + (f", under the {cfg.max_float_days_consumed:g} d cap" if ctx.is_near_critical else "")
              + (f" ({spent / own:.0%} of its {own:g} d)" if own and own > 0 and spent > 0 else ""))
    if proposal.kind is ProposalKind.SPLIT:
        return _approve("split_within_float_ok",
                        f"Split keeps every half inside its compliant window and {within}. Approved.")
    return _approve("within_policy",
                    f"Placement holds every constraint and {within}. Approved.")


__all__ = [
    "PolicyConfig", "load_policy", "GateContext", "MilestoneRisk",
    "evaluate_policy",
    # rules exported so tests can call them in isolation
    "fail_closed_on_stale_forecast", "no_precedence_violation",
    "no_move_inspection_hold_point", "no_move_past_milestone",
    "no_out_of_spec_application", "max_float_days_consumed",
    "no_auto_night_work", "wbgt_rest_ratio_escalate",
]
