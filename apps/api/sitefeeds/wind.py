"""Site-level wind feed — the one field FortyGuard does not provide.

Open-Meteo first (free, no key). NWS is a documented fallback, not the default.
Wind is a *site* scalar, not a 60 m field — say that in every series we emit.

    python -m apps.api.sitefeeds.wind --write-fixture

REPLAY_MODE=true (default) reads data/fixtures/wind_open_meteo.json.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "data" / "fixtures" / "wind_open_meteo.json"

# FAB2 hero centroid (WF-FAB2-07 / site mean is within a few hundred metres).
DEFAULT_LAT = 33.78579
DEFAULT_LON = -112.16694
TZ = "America/Phoenix"

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


class WindFeedError(RuntimeError):
    pass


def _replay_mode(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get("REPLAY_MODE", "true").lower() in ("1", "true", "yes")


def _parse_iso(ts: str) -> datetime:
    # Open-Meteo hourly stamps are "2026-08-22T14:00" (no offset) in the requested tz.
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=-7)))
    return dt


def _points_from_open_meteo(payload: dict) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    speeds = hourly.get("wind_speed_10m") or []
    dirs = hourly.get("wind_direction_10m") or [None] * len(times)
    points = []
    for ts, spd, direc in zip(times, speeds, dirs):
        points.append(
            {
                "ts": _parse_iso(ts).isoformat(),
                "wind_ms": None if spd is None else float(spd),
                "wind_dir_deg": None if direc is None else float(direc) % 360.0,
                "source": "open_meteo",
                "height_m": 10,
                "spatial": "site_scalar",
            }
        )
    return points


class WindFeed:
    """Hourly 10 m wind at one lat/lon. Not spatially resolved."""

    def __init__(
        self,
        *,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        replay_mode: bool | None = None,
        fixture_path: Path | None = None,
        url: str | None = None,
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.replay_mode = _replay_mode(replay_mode)
        self.fixture_path = fixture_path or FIXTURE
        self.url = url or os.environ.get("WIND_FEED_URL") or OPEN_METEO_FORECAST

    def _load_fixture(self) -> dict:
        if not self.fixture_path.exists():
            raise FileNotFoundError(
                f"REPLAY_MODE=true but no wind fixture at {self.fixture_path}"
            )
        return json.loads(self.fixture_path.read_text(encoding="utf-8"))

    async def fetch(
        self,
        *,
        start: datetime | None = None,
        hours: int = 48,
        forecast_days: int = 3,
        force_live: bool = False,
    ) -> dict[str, Any]:
        if self.replay_mode and not force_live:
            raw = self._load_fixture()
            return self._bundle(raw, replay=True)

        params: dict[str, Any] = {
            "latitude": self.lat,
            "longitude": self.lon,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
            "timezone": TZ,
        }
        if start is not None:
            end = start + timedelta(hours=hours)
            params["start_date"] = start.date().isoformat()
            params["end_date"] = end.date().isoformat()
            url = OPEN_METEO_ARCHIVE if start.date().isoformat() < "2026-08-01" else self.url
        else:
            params["forecast_days"] = forecast_days
            url = self.url

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, params=params)
            if r.status_code >= 400:
                raise WindFeedError(f"wind feed {r.status_code}: {r.text[:300]}")
            raw = r.json()

        return self._bundle(raw, replay=False)

    def _bundle(self, raw: dict, *, replay: bool) -> dict[str, Any]:
        points = _points_from_open_meteo(raw)
        return {
            "schema": "workface.wind.v1",
            "lat": raw.get("latitude", self.lat),
            "lon": raw.get("longitude", self.lon),
            "tz": TZ,
            "spatial": "site_scalar",
            "note": (
                "FortyGuard env_params has no wind. This is a site-level scalar "
                "from Open-Meteo (10 m). It is NOT resolved per 60 m tile."
            ),
            "replay": replay,
            "points": points,
            "raw": raw if not replay else {"fixture": str(self.fixture_path.name)},
        }

    def at(self, bundle: dict, ts: datetime) -> dict[str, Any] | None:
        """Nearest hour ≤ ts. Site scalar — same value for every work face."""
        target = ts.astimezone(timezone(timedelta(hours=-7)))
        best = None
        for p in bundle.get("points") or []:
            pt = _parse_iso(p["ts"])
            if pt <= target:
                best = p
            else:
                break
        return best

    def write_fixture(self, raw: dict, path: Path | None = None) -> Path:
        dest = path or self.fixture_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return dest


async def fetch_and_maybe_write(*, write_fixture: bool, hours: int, live: bool) -> dict:
    feed = WindFeed(replay_mode=not live)
    bundle = await feed.fetch(hours=hours, force_live=live)
    if write_fixture and live:
        # Persist the raw Open-Meteo body so replay never needs the network.
        raw = bundle.get("raw") if isinstance(bundle.get("raw"), dict) else None
        if raw and "hourly" in raw:
            feed.write_fixture(raw)
        elif not feed.fixture_path.exists():
            raise WindFeedError("live fetch did not return an Open-Meteo hourly body")
    return bundle


def main(argv: list[str] | None = None) -> int:
    import asyncio

    parser = argparse.ArgumentParser(description="Fetch site-level wind (Open-Meteo).")
    parser.add_argument("--write-fixture", action="store_true")
    parser.add_argument("--live", action="store_true", help="Hit Open-Meteo even if REPLAY_MODE=true.")
    parser.add_argument("--hours", type=int, default=48)
    args = parser.parse_args(argv)

    bundle = asyncio.run(
        fetch_and_maybe_write(write_fixture=args.write_fixture, hours=args.hours, live=args.live)
    )
    n = len(bundle.get("points") or [])
    print(f"wind points={n} replay={bundle.get('replay')} lat={bundle.get('lat')} lon={bundle.get('lon')}")
    if n:
        p0 = bundle["points"][0]
        print(f"  first {p0['ts']}  {p0['wind_ms']} m/s  {p0['wind_dir_deg']}°")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
