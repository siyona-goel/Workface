"""Supabase service-role client for the worker (T2 Day 8).

Uses SUPABASE_URL + SUPABASE_SERVICE_KEY (never the anon key).
GitHub Actions injects these as secrets.
"""

from __future__ import annotations

import os
from typing import Any


def get_supabase():
    """Return a supabase-py client or raise with a clear message."""
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY required to push worker results. "
            "Set them in the environment or GitHub Actions secrets."
        )
    try:
        from supabase import create_client
    except ImportError as e:
        raise RuntimeError(
            "Install supabase: pip install supabase"
        ) from e
    return create_client(url, key)


def env_ready() -> bool:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    return bool(url and key)
