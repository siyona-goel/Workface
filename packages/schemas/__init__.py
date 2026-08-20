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

from . import activity, window_eval  # noqa: F401

__all__ = ["activity", "window_eval"]
