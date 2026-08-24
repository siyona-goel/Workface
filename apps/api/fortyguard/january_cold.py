"""Day-9 January cold call — persistence / direction: below.

Kills the "this is just heat" objection: one winter window where the floor
matters, not the ceiling.

    # REPLAY synthetic (default)
    python -m apps.api.fortyguard.january_cold --write

    # LIVE (costs credits)
    python -m apps.api.fortyguard.january_cold --write --live

Writes:
  data/fixtures/historical/january_cold_manifest.json
  data/fixtures/historical/raw/january_*_persistence_below.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
AOI = REPO / "data" / "aoi" / "tile_clusters.geojson"
OUT_DIR = REPO / "data" / "fixtures" / "historical"
RAW_DIR = OUT_DIR / "raw"

# Cold-weather floor used in ACI 306 trigger band (see trade registry)
THRESHOLD_BELOW_C = 4.0
YEAR = 2024  # January inside FG historical range
GRANULARITY = 100


def _load_hero_aoi() -> dict[str, Any]:
    if not AOI.exists():
        raise FileNotFoundError(f"missing {AOI} — run AOI clustering first")
    fc = json.loads(AOI.read_text())
    # Prefer FAB2 hero cluster
    for f in fc["features"]:
        props = f.get("properties") or {}
        if props.get("id") == "AOI-FAB2" or "FAB2" in (props.get("structure_ids") or []):
            return {"id": props.get("id") or "AOI-FAB2", "geometry": f["geometry"], "properties": props}
    f0 = fc["features"][0]
    props = f0.get("properties") or {}
    return {"id": props.get("id") or "AOI-0", "geometry": f0["geometry"], "properties": props}


def _body(geom: dict) -> dict[str, Any]:
    return {
        "polygon_aoi": {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": geom}],
        },
        "date_time": {
            "start_date": f"{YEAR}-01-01",
            "end_date": f"{YEAR}-01-31",
            "filter_type": 4,
        },
        "granularity": GRANULARITY,
        "analytic_type": "persistence",
        "threshold": THRESHOLD_BELOW_C,
        "direction": "below",
    }


def _synthetic_tiles(cluster: dict) -> list[dict[str, Any]]:
    props = cluster["properties"]
    n = max(8, min(int(props.get("est_tiles_plan") or 40), 60))
    ring = cluster["geometry"]["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    west, east, south, north = min(xs), max(xs), min(ys), max(ys)
    cols = max(2, int(math.sqrt(n)))
    rows = max(2, math.ceil(n / cols))
    tiles = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n:
                break
            lon = west + (c + 0.5) * (east - west) / cols
            lat = south + (r + 0.5) * (north - south) / rows
            seed = f"jan-cold|{cluster['id']}|{idx}"
            u = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            # Phoenix January: some nights below 4 °C — longest run a few hours
            value = round(2.0 + u * 10.0, 2)
            tiles.append(
                {
                    "tile_id": f"{cluster['id']}-jan-r{r:02d}c{c:02d}",
                    "centroid_lon": round(lon, 7),
                    "centroid_lat": round(lat, 7),
                    "value": value,
                }
            )
            idx += 1
    return tiles


def write_replay(cluster: dict) -> dict[str, Any]:
    tiles = _synthetic_tiles(cluster)
    fg_id = f"replay-jan-{YEAR}-persistence-below"
    window = {
        "year": YEAR,
        "start_date": f"{YEAR}-01-01",
        "end_date": f"{YEAR}-01-31",
        "filter_type": 4,
        "granularity_m": GRANULARITY,
        "analytic_type": "persistence",
        "threshold_c": THRESHOLD_BELOW_C,
        "direction": "below",
        "units": "hour",
        "tiles": tiles,
        "stats": None,
        "fg_activity_id": fg_id,
        "note": (
            "January persistence/below — cold floor, not heat ceiling. "
            "REPLAY synthetic for demo slide; replace with --live once."
        ),
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = {
        "error": False,
        "status_code": 200,
        "message": "Completed",
        "data": {
            "activity_id": fg_id,
            "status": "Completed",
            "result": {"map_data": {"type": "FeatureCollection", "features": []}, "stats_data": {}},
        },
        "_meta": {
            "analytic_type": "persistence",
            "direction": "below",
            "threshold_c": THRESHOLD_BELOW_C,
            "month": "January",
            "year": YEAR,
        },
    }
    raw_path = RAW_DIR / f"january_{YEAR}_persistence_below.json"
    raw_path.write_text(json.dumps(raw, indent=2))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "replay": True,
        "purpose": "Day-9 January cold slide — persistence direction=below",
        "year": YEAR,
        "month": 1,
        "analytic_type": "persistence",
        "direction": "below",
        "threshold_c": THRESHOLD_BELOW_C,
        "tile_cluster_id": cluster["id"],
        "n_tiles": len(tiles),
        "median_persistence_h": sorted(t["value"] for t in tiles)[len(tiles) // 2],
        "raw": str(raw_path.relative_to(REPO)),
        "window": window,
        "slide_line": (
            f"January {YEAR}: tiles show multi-hour runs below {THRESHOLD_BELOW_C} °C "
            "(persistence/below) — cold-weather protection, not a heat alarm."
        ),
    }
    man_path = OUT_DIR / "january_cold_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


async def write_live(cluster: dict) -> dict[str, Any]:
    from apps.api.fortyguard.client import FortyGuardClient

    client = FortyGuardClient(replay_mode=False)
    client.max_poll_s = 600.0
    body = _body(cluster["geometry"])
    result = await client.call("heatmap", body, force_live=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"january_{YEAR}_persistence_below_live.json"
    raw_path.write_text(json.dumps(result, indent=2, default=str))
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "replay": False,
        "purpose": "Day-9 January cold slide — live FortyGuard capture",
        "year": YEAR,
        "analytic_type": "persistence",
        "direction": "below",
        "threshold_c": THRESHOLD_BELOW_C,
        "tile_cluster_id": cluster["id"],
        "fg_activity_id": (result.get("data") or {}).get("activity_id"),
        "raw": str(raw_path.relative_to(REPO)),
        "slide_line": (
            f"January {YEAR} live persistence/below @ {THRESHOLD_BELOW_C} °C on {cluster['id']}."
        ),
    }
    (OUT_DIR / "january_cold_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="January persistence/below cold-floor capture")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args(argv)
    if not args.write:
        ap.print_help()
        return 1
    cluster = _load_hero_aoi()
    if args.live:
        import asyncio

        man = asyncio.run(write_live(cluster))
    else:
        man = write_replay(cluster)
    print(json.dumps({k: man[k] for k in man if k != "window"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
