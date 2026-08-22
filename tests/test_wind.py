"""T2 Day 3 — site-level wind feed (Open-Meteo), replay from fixture."""

from __future__ import annotations

from datetime import datetime, timedelta

from apps.api.sitefeeds.wind import FIXTURE, WindFeed, _points_from_open_meteo


def test_fixture_exists_and_parses() -> None:
    assert FIXTURE.exists(), "commit data/fixtures/wind_open_meteo.json — a fixture on a laptop is not a fixture"
    feed = WindFeed(replay_mode=True)
    raw = feed._load_fixture()
    points = _points_from_open_meteo(raw)
    assert len(points) >= 24
    assert all(p["spatial"] == "site_scalar" for p in points)
    assert all(p["wind_ms"] is None or p["wind_ms"] >= 0 for p in points)


def test_replay_bundle_is_site_scalar() -> None:
    import asyncio

    feed = WindFeed(replay_mode=True)
    bundle = asyncio.run(feed.fetch())
    assert bundle["replay"] is True
    assert bundle["spatial"] == "site_scalar"
    assert "NOT resolved per 60 m tile" in bundle["note"]
    ts = datetime.fromisoformat(bundle["points"][3]["ts"])
    hit = feed.at(bundle, ts + timedelta(minutes=20))
    assert hit is not None
    assert hit["wind_ms"] == bundle["points"][3]["wind_ms"]
