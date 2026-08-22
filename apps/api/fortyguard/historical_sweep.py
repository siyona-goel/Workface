"""Day-4 historical sweep — fetch only, cache forever.

One August window per year 2019→2025, per AOI cluster:
  exceedance  × above / below
  persistence × above / below

= 5 AOIs × 7 years × 4 analytics = 140 calls (matches data/aoi/plan.json).

    # REPLAY (default): write schema-valid fixtures from a deterministic generator
    # so T3 can build climatology priors without burning credits.
    python -m apps.api.fortyguard.historical_sweep --write

    # LIVE: hit FortyGuard (REPLAY_MODE ignored for this run)
    python -m apps.api.fortyguard.historical_sweep --write --live

Outputs:
  data/fixtures/historical/sweep_bundle.json          # HistoricalSweepBundle
  data/fixtures/historical/raw/{cluster}_{year}_{analytic}_{direction}.json
  data/fixtures/historical/manifest.json              # call plan + counts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[3]
AOI_CLUSTERS = REPO / "data" / "aoi" / "tile_clusters.geojson"
BUDGET_PATH = REPO / "config" / "budget.yaml"
TRADE_WINDOWS = REPO / "data" / "trade_windows.json"
OUT_DIR = REPO / "data" / "fixtures" / "historical"
RAW_DIR = OUT_DIR / "raw"

# Representative thresholds for the 140-call budget (1 above + 1 below).
# Full registry mins/maxs are recorded in requested_thresholds_c for T3.
DEFAULT_ABOVE_C = 35.0   # common air ceiling (coating / hot-weather trigger band)
DEFAULT_BELOW_C = 4.0    # ACI 306 cold-weather trigger

Analytic = Literal["exceedance", "persistence"]
Direction = Literal["above", "below"]


def _load_budget() -> dict[str, Any]:
    text = BUDGET_PATH.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
        return {
            "climatology_years": years,
            "climatology_analytics_per_year": 4,
            "granularity_plan_m": 100,
        }


def _registry_thresholds() -> list[float]:
    """Distinct band thresholds from T3's trade window registry."""
    if not TRADE_WINDOWS.exists():
        return [DEFAULT_BELOW_C, DEFAULT_ABOVE_C]
    raw = json.loads(TRADE_WINDOWS.read_text())
    items = raw if isinstance(raw, list) else raw.get("trades") or list(raw.values())
    vals: set[float] = set()
    for t in items:
        for c in t.get("constraints") or []:
            if c.get("type") != "band":
                continue
            for k in ("t_min_c", "t_max_c"):
                if c.get(k) is not None:
                    vals.add(float(c[k]))
    return sorted(vals) if vals else [DEFAULT_BELOW_C, DEFAULT_ABOVE_C]


def _load_clusters() -> list[dict[str, Any]]:
    if not AOI_CLUSTERS.exists():
        raise FileNotFoundError(
            f"Missing {AOI_CLUSTERS}. Run: python -m apps.api.fortyguard.aoi --write"
        )
    fc = json.loads(AOI_CLUSTERS.read_text())
    out = []
    for f in fc["features"]:
        props = f.get("properties") or {}
        out.append(
            {
                "id": props.get("id") or props.get("tile_cluster_id"),
                "geometry": f["geometry"],
                "properties": props,
            }
        )
    return out


def _polygon_aoi(geom: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": geom,
            }
        ],
    }


def _heatmap_body(
    geom: dict,
    *,
    year: int,
    analytic: Analytic,
    direction: Direction,
    threshold_c: float,
    granularity: int,
) -> dict[str, Any]:
    return {
        "polygon_aoi": _polygon_aoi(geom),
        "date_time": {
            "start_date": f"{year}-08-01",
            "end_date": f"{year}-08-31",
            "filter_type": 4,
        },
        "granularity": granularity,
        "analytic_type": analytic,
        "threshold": threshold_c,
        "direction": direction,
    }


def _stable_unit(seed: str) -> float:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _synthetic_tiles(
    cluster: dict[str, Any],
    *,
    year: int,
    analytic: Analytic,
    direction: Direction,
    threshold_c: float,
) -> list[dict[str, Any]]:
    """Deterministic tile readings so REPLAY is stable across machines."""
    props = cluster["properties"]
    est = int(props.get("est_tiles_plan") or 40)
    n = max(8, min(est, 80))
    geom = cluster["geometry"]
    ring = geom["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    west, east = min(xs), max(xs)
    south, north = min(ys), max(ys)

    cols = max(2, int(math.sqrt(n)))
    rows = max(2, math.ceil(n / cols))
    tiles: list[dict[str, Any]] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n:
                break
            lon = west + (c + 0.5) * (east - west) / cols
            lat = south + (r + 0.5) * (north - south) / rows
            seed = f"{cluster['id']}|{year}|{analytic}|{direction}|{threshold_c}|{idx}"
            u = _stable_unit(seed)

            # Phoenix August: hot days, almost never below 4 °C.
            if direction == "below":
                # hours under floor ≈ 0 in August
                if analytic == "exceedance":
                    value = round(u * 2.0, 2)  # 0–2 h
                else:
                    value = round(u * 1.0, 2)  # persistence 0–1 h
            else:
                # hours above 35 °C: substantial daytime exceedance
                # slightly warmer trend in later years
                year_bump = (year - 2019) * 3.0
                if analytic == "exceedance":
                    value = round(180 + u * 120 + year_bump, 2)  # ~180–300+ h / month
                else:
                    value = round(8 + u * 28 + year_bump * 0.1, 2)  # longest run ~8–36 h

            tiles.append(
                {
                    "tile_id": f"{cluster['id']}-r{r:02d}c{c:02d}",
                    "centroid_lon": round(lon, 7),
                    "centroid_lat": round(lat, 7),
                    "value": value,
                }
            )
            idx += 1
    return tiles


def _window_record(
    cluster: dict[str, Any],
    *,
    year: int,
    analytic: Analytic,
    direction: Direction,
    threshold_c: float,
    granularity: int,
    tiles: list[dict[str, Any]],
    fg_activity_id: str,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    units = "hour"
    return {
        "year": year,
        "start_date": f"{year}-08-01",
        "end_date": f"{year}-08-31",
        "filter_type": 4,
        "granularity_m": granularity,
        "analytic_type": analytic,
        "threshold_c": threshold_c,
        "direction": direction,
        "units": units,
        "tiles": tiles,
        "stats": stats,
        "fg_activity_id": fg_activity_id,
    }


def _reduce_map_data(result: dict[str, Any], cluster_id: str) -> list[dict[str, Any]]:
    """Pull tile centroid + analytic value from a live heatmap result."""
    data = (result.get("data") or {}).get("result") or {}
    md = data.get("map_data") or {}
    feats = md.get("features") or []
    tiles: list[dict[str, Any]] = []
    for i, f in enumerate(feats):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        ring = (geom.get("coordinates") or [[]])[0]
        if not ring:
            continue
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        # FortyGuard property names vary by analytic; try common keys
        value = None
        for k in (
            "value",
            "exceedance",
            "persistence",
            "hours",
            "average_temperature",
            "max_temperature",
        ):
            if props.get(k) is not None:
                value = float(props[k])
                break
        tiles.append(
            {
                "tile_id": str(props.get("tile_id", f"{cluster_id}-{i}")),
                "centroid_lon": round(lon, 7),
                "centroid_lat": round(lat, 7),
                "value": value,
            }
        )
    return tiles


def build_call_plan(
    clusters: list[dict[str, Any]],
    years: list[int],
    granularity: int,
) -> list[dict[str, Any]]:
    """Exact 140-call plan: 4 analytics × years × AOIs."""
    plan = []
    for cluster in clusters:
        for year in years:
            for analytic, direction, thr in (
                ("exceedance", "above", DEFAULT_ABOVE_C),
                ("exceedance", "below", DEFAULT_BELOW_C),
                ("persistence", "above", DEFAULT_ABOVE_C),
                ("persistence", "below", DEFAULT_BELOW_C),
            ):
                plan.append(
                    {
                        "cluster_id": cluster["id"],
                        "year": year,
                        "analytic": analytic,
                        "direction": direction,
                        "threshold_c": thr,
                        "granularity": granularity,
                        "body": _heatmap_body(
                            cluster["geometry"],
                            year=year,
                            analytic=analytic,  # type: ignore[arg-type]
                            direction=direction,  # type: ignore[arg-type]
                            threshold_c=thr,
                            granularity=granularity,
                        ),
                    }
                )
    return plan


async def _run_live(plan: list[dict[str, Any]], clusters_by_id: dict[str, dict]) -> list[dict]:
    from apps.api.fortyguard.client import FortyGuardClient

    client = FortyGuardClient(replay_mode=False)
    # Historical = long polls
    client.max_poll_s = 600.0
    windows: list[dict[str, Any]] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for i, job in enumerate(plan, 1):
        cid = job["cluster_id"]
        print(
            f"[{i}/{len(plan)}] live {cid} {job['year']} "
            f"{job['analytic']}/{job['direction']} @{job['threshold_c']}°C"
        )
        result = await client.call("heatmap", job["body"], force_live=True)
        raw_name = (
            f"{cid}_{job['year']}_{job['analytic']}_{job['direction']}.json"
        )
        (RAW_DIR / raw_name).write_text(json.dumps(result, indent=2, default=str))

        status = (result.get("data") or {}).get("status")
        fg_id = (result.get("data") or {}).get("activity_id") or f"live-{uuid.uuid4()}"
        tiles = _reduce_map_data(result, cid) if status == "Completed" else []
        stats_raw = ((result.get("data") or {}).get("result") or {}).get("stats_data") or {}
        tstats = stats_raw.get("temperature_stats") or stats_raw.get("Temperature_stats")
        stats = None
        if isinstance(tstats, dict):
            stats = {
                "minimum": tstats.get("minimum"),
                "maximum": tstats.get("maximum"),
                "mean": tstats.get("mean"),
                "standard_deviation": tstats.get("standard_deviation"),
            }
        windows.append(
            {
                "tile_cluster_id": cid,
                "window": _window_record(
                    clusters_by_id[cid],
                    year=job["year"],
                    analytic=job["analytic"],
                    direction=job["direction"],
                    threshold_c=job["threshold_c"],
                    granularity=job["granularity"],
                    tiles=tiles,
                    fg_activity_id=str(fg_id),
                    stats=stats,
                ),
            }
        )
    return windows


def _run_replay(plan: list[dict[str, Any]], clusters_by_id: dict[str, dict]) -> list[dict]:
    """Deterministic synthetic sweep — no network, permanent cache shape."""
    windows: list[dict[str, Any]] = []
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for i, job in enumerate(plan, 1):
        cid = job["cluster_id"]
        print(
            f"[{i}/{len(plan)}] replay {cid} {job['year']} "
            f"{job['analytic']}/{job['direction']}"
        )
        tiles = _synthetic_tiles(
            clusters_by_id[cid],
            year=job["year"],
            analytic=job["analytic"],
            direction=job["direction"],
            threshold_c=job["threshold_c"],
        )
        fg_id = f"replay-{cid}-{job['year']}-{job['analytic']}-{job['direction']}"
        window = _window_record(
            clusters_by_id[cid],
            year=job["year"],
            analytic=job["analytic"],
            direction=job["direction"],
            threshold_c=job["threshold_c"],
            granularity=job["granularity"],
            tiles=tiles,
            fg_activity_id=fg_id,
            stats=None,
        )
        # stub raw status payload for provenance parity with live path
        raw = {
            "error": False,
            "status_code": 200,
            "message": "Completed",
            "data": {
                "activity_id": fg_id,
                "status": "Completed",
                "result": {
                    "map_data": {"type": "FeatureCollection", "features": []},
                    "stats_data": {},
                    "_note": "REPLAY synthetic — replace with live capture via --live",
                },
            },
        }
        raw_name = f"{cid}_{job['year']}_{job['analytic']}_{job['direction']}.json"
        (RAW_DIR / raw_name).write_text(json.dumps(raw, indent=2))
        windows.append({"tile_cluster_id": cid, "window": window})
    return windows


def assemble_bundle(
    clusters: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    *,
    years: list[int],
    replay: bool,
) -> dict[str, Any]:
    by_cluster: dict[str, list] = {c["id"]: [] for c in clusters}
    for row in window_rows:
        by_cluster[row["tile_cluster_id"]].append(row["window"])

    sweeps = []
    for c in clusters:
        sweeps.append(
            {
                "tile_cluster_id": c["id"],
                "aoi_geojson": c["geometry"],
                "month": 8,
                "years": years,
                "requested_thresholds_c": _registry_thresholds(),
                "windows": by_cluster[c["id"]],
            }
        )

    return {
        "schema_version": "1.0.0",
        "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_id": "NPX-FAB-P2",
        "tz": "America/Phoenix",
        "tier": "plan",
        "sweeps": sweeps,
        "cached_forever": True,
        "replay": replay,
    }


def write_outputs(
    bundle: dict[str, Any],
    plan: list[dict[str, Any]],
    *,
    replay: bool,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = OUT_DIR / "sweep_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, default=str))

    manifest = {
        "generated_at": bundle["generated_at"],
        "replay": replay,
        "n_calls": len(plan),
        "n_aoi": len({j["cluster_id"] for j in plan}),
        "years": sorted({j["year"] for j in plan}),
        "analytics": ["exceedance_above", "exceedance_below", "persistence_above", "persistence_below"],
        "thresholds_c": {"above": DEFAULT_ABOVE_C, "below": DEFAULT_BELOW_C},
        "registry_thresholds_c": _registry_thresholds(),
        "bundle": str(bundle_path.relative_to(REPO)),
        "raw_dir": str(RAW_DIR.relative_to(REPO)),
        "cached_forever": True,
        "note": (
            "REPLAY synthetic values — run with --live once to replace with real "
            "FortyGuard captures. filter_type=4, one August month per year."
            if replay
            else "Live FortyGuard captures. Cache forever; do not re-fetch."
        ),
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {bundle_path}")
    print(f"wrote {OUT_DIR / 'manifest.json'}")
    print(f"raw payloads: {RAW_DIR} ({len(list(RAW_DIR.glob('*.json')))} files)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day-4 historical August sweep 2019→2025")
    parser.add_argument("--write", action="store_true", help="Write fixtures to data/fixtures/historical/")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Hit FortyGuard for real (costs credits). Default is REPLAY synthetic.",
    )
    parser.add_argument("--dry-plan", action="store_true", help="Print call plan only")
    args = parser.parse_args(argv)

    budget = _load_budget()
    years = list(budget.get("climatology_years") or list(range(2019, 2026)))
    granularity = int(budget.get("granularity_plan_m") or 100)

    clusters = _load_clusters()
    clusters_by_id = {c["id"]: c for c in clusters}
    plan = build_call_plan(clusters, years, granularity)

    print(f"AOIs={len(clusters)} years={years} calls={len(plan)} (expect 140)")
    if args.dry_plan:
        for j in plan[:8]:
            print(
                f"  {j['cluster_id']} {j['year']} {j['analytic']}/{j['direction']} "
                f"thr={j['threshold_c']}"
            )
        print(f"  ... ({len(plan)} total)")
        return 0

    if not args.write:
        parser.print_help()
        print("\nUse --write (and optionally --live).")
        return 1

    if args.live:
        import asyncio

        window_rows = asyncio.run(_run_live(plan, clusters_by_id))
        replay = False
    else:
        window_rows = _run_replay(plan, clusters_by_id)
        replay = True

    bundle = assemble_bundle(clusters, window_rows, years=years, replay=replay)
    write_outputs(bundle, plan, replay=replay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
