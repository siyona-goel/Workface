"""WORKFACE shared contracts.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# These are different things. They will collide if you blur them.
# ---------------------------------------------------------------------------

This is the ONE shared folder. Rules (WORKFACE_REPO_GUIDE.md):
  - Day 1: all three of you edit it together in one sitting, then commit once.
  - After Day 1, any change needs a PR that tags the other two.
  - Never rename a field silently — rename in one PR, everyone updates in the next.
  - Keep the Pydantic and Zod versions side by side and matching.
"""

from . import (  # noqa: F401
    activity,             # #1 T3 -> T2  project schedule
    thermal_series,       # #2 T2 -> T3  hourly air temp + env_params + wind
    historical_readings,  # #3 T2 -> T3  raw 7-year sweep -> climatology priors
    twin_segmentation,    # #4 T2 -> T3  raw satellite + streetview -> surface twin
    window_eval,          # #5 T3 -> T1  the ribbon contract
    agent_trace,          # #6 T3 -> T1  the agent decision log
    record,               # #6/#7 T3 -> T1/T2  hash chain + thermal certificate
)

__all__ = [
    "activity",
    "thermal_series",
    "historical_readings",
    "twin_segmentation",
    "window_eval",
    "agent_trace",
    "record",
]
