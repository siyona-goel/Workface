"""
WORKFACE — the planner sentence for a Tier-0 prior.  T3, Day 5, Task B.

A planner does not read a probability table. This turns one `TradePriorSummary`
into the sentence the schedule specifies:

    "This work face had a compliant coating window on 34% of August mornings over
     seven years, opening at a median of 06:40 and closing at 09:10."

The modelled-timing caveat is CARRIED, never stripped (WORKFACE_T3_DAY56 §4 /
§2.3): a Tier-0 number is a PROBABILITY, NOT A FORECAST, and its opening/closing
hours are modelled off the diurnal shape, not observed. This string goes on a
slide and into the UI, so it is a deliverable, not a debug helper — its exact
text is asserted in tests/test_priors.py.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from apps.api.climatology.priors import Coverage, HourSource, TradePriorSummary

_ONES = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}

# Carried on every modelled-timing sentence; never stripped.
MODELLED_CAVEAT = "Opening and closing times are modelled from the diurnal shape, not observed."


def _years_word(n: int) -> str:
    return _ONES.get(n, str(n))


def _short_trade(display_name: str) -> str:
    """'Cast-in-place concrete — hot weather' -> 'concrete'; used to fill the
    '{trade} window' slot in the schedule's canonical sentence. Falls back to the
    lower-cased display name when no keyword is recognised."""
    d = display_name.lower()
    for key in ("coating", "concrete", "fireproofing", "masonry", "sealant",
                "paving", "welding", "anchor", "marking"):
        if key in d:
            return key
    return d


def compliant_window_sentence(
    *,
    trade_word: str,
    pct_mornings: int,
    open_hhmm: str,
    close_hhmm: str,
    n_years: int,
    modelled_timing: bool = True,
) -> str:
    """The schedule's canonical compliant-morning-window sentence.

    Kept as an explicit-parameter primitive so its exact text can be asserted
    independent of any particular sweep.
    """
    s = (f"This work face had a compliant {trade_word} window on {pct_mornings}% of "
         f"August mornings over {_years_word(n_years)} years, opening at a median of "
         f"{open_hhmm} and closing at {close_hhmm}.")
    if modelled_timing:
        s += " " + MODELLED_CAVEAT
    return s


def exceedance_sentence(summary: TradePriorSummary) -> str:
    """The hot-ceiling phrasing the sweep actually supports (WORKFACE_T3_DAY56 §2.3):

        "This work face exceeded the 35 C concrete discharge limit for a median of
         275 hours across seven Augusts — 37% of the month. Modelled crossing at
         10:40, closing at 18:10."
    """
    thr = f"{summary.threshold_c:g}" if summary.threshold_c is not None else "?"
    return (
        f"This work face exceeded the {thr} C {_short_trade(summary.trade_display_name)} "
        f"discharge limit for a median of {summary.median_hours_exceeded:g} hours across "
        f"{_years_word(summary.n_years)} Augusts — {summary.pct_of_month}% of the month. "
        f"Modelled crossing at {summary.cross_up_hhmm}, closing at {summary.cross_down_hhmm}."
    )


def sentence_for(summary: TradePriorSummary) -> str:
    """Dispatch to the right phrasing for a summary, or state the gap plainly.

    * insufficient_threshold -> the honest one-liner naming what is missing.
    * modelled hot ceiling   -> the exceedance sentence (crossing hours modelled).
    * observed floor         -> a compliance-rate sentence (no hour claim).
    """
    if summary.coverage is Coverage.INSUFFICIENT_THRESHOLD:
        return (f"No Tier-0 prior for {summary.trade_display_name.lower()}: "
                f"{summary.reason}")

    if summary.coverage is Coverage.MODELLED_HOUR:
        return exceedance_sentence(summary)

    # Observed floor: essentially always compliant in August; no hour-of-day claim.
    pct = round(100.0 * (summary.p_open_overall or 0.0))
    return (f"This work face met the {summary.trade_display_name.lower()} floor on a "
            f"climatological {pct}% of August hours across {_years_word(summary.n_years)} "
            f"years (observed, not modelled by hour) — cold is not the August risk here.")


__all__ = [
    "MODELLED_CAVEAT", "compliant_window_sentence", "exceedance_sentence", "sentence_for",
]
