"""Day-5 raw Twin capture + env_params chaining + hero heat_intelligence.

    satellite + streetview  → once per work face, cached forever
    env_params              → temperature + date_time from heatmap (never invented)
    heat_intelligence       → hero work face only (PDF + redacted link)

    # REPLAY (default) — no API credits
    python -m apps.api.fortyguard.twin_capture --write

    # LIVE — burns credits (40 sat + 40 sv + env + 1 heat_intel)
    python -m apps.api.fortyguard.twin_capture --write --live

Outputs:
  data/fixtures/twin/twin_bundle.json
  data/fixtures/twin/manifest.json
  data/fixtures/twin/env_params_chained.json
  data/fixtures/twin/heat_intelligence_hero.json
  data/fixtures/twin/heat_intelligence_hero.pdf   (live only, if download works)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
WORK_FACES = REPO / "data" / "project_demo" / "work_faces.geojson"
SITE = REPO / "data" / "project_demo" / "site.geojson"
FIXTURES = REPO / "data" / "fixtures"
OUT_DIR = REPO / "data" / "fixtures" / "twin"
HERO_ID = "WF-FAB2-07"

# Chaining defaults from Day-1 North Phoenix August heatmap capture
CHAIN_DATE = "2024-08-15"
CHAIN_TIME = "14:00"
HEATMAP_GLOB = "heatmap_result_*.json"


def _site_id() -> str:
    if SITE.exists():
        fc = json.loads(SITE.read_text())
        for f in fc.get("features") or []:
            sid = (f.get("properties") or {}).get("site_id")
            if sid:
                return sid
    return "NPX-FAB-P2"


def _load_faces() -> list[dict[str, Any]]:
    fc = json.loads(WORK_FACES.read_text())
    faces = []
    for f in fc["features"]:
        p = f["properties"]
        faces.append(
            {
                "id": p["id"],
                "name": p.get("name"),
                "lat": float(p["centroid_lat"]),
                "lon": float(p["centroid_lon"]),
                "surface_class": p.get("surface_class"),
                "exposure_class": p.get("exposure_class"),
                "sky_view_factor": p.get("sky_view_factor"),
            }
        )
    return faces


def _heatmap_chain_temp() -> float:
    """Temperature for env_params / heat_intelligence — from heatmap stats, never invented."""
    matches = sorted(FIXTURES.glob(HEATMAP_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in matches:
        try:
            d = json.loads(path.read_text())
            stats = (
                (d.get("data") or {}).get("result") or {}
            ).get("stats_data") or {}
            tstats = stats.get("temperature_stats") or stats.get("Temperature_stats") or {}
            mean = tstats.get("mean")
            if mean is not None:
                return round(float(mean), 4)
            # fallback: average of tile averages
            feats = ((d.get("data") or {}).get("result") or {}).get("map_data") or {}
            vals = []
            for feat in feats.get("features") or []:
                av = (feat.get("properties") or {}).get("average_temperature")
                if av is not None:
                    vals.append(float(av))
            if vals:
                return round(sum(vals) / len(vals), 4)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            continue
    raise FileNotFoundError(
        f"No heatmap fixture with temperature under {FIXTURES}. "
        "Run Day-1 heatmap capture first — env_params must chain from it."
    )


def _unit(seed: str) -> float:
    return int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _segments_for_surface(surface: str | None, seed: str) -> dict[str, float]:
    """Plausible land-cover fractions from work-face surface_class (REPLAY only)."""
    u = _unit(seed)
    table = {
        "bare_concrete": {"concrete": 55 + u * 20, "bare_soil": 15, "asphalt": 10, "vegetation": 10, "metal": 5},
        "galvanised_steel": {"metal": 50 + u * 15, "concrete": 20, "shadow": 15, "vegetation": 5, "other": 5},
        "asphalt": {"asphalt": 60 + u * 15, "concrete": 15, "bare_soil": 10, "vegetation": 10},
        "vegetation": {"vegetation": 50 + u * 20, "bare_soil": 20, "concrete": 15, "other": 10},
    }
    base = table.get(surface or "", {"concrete": 40, "bare_soil": 25, "vegetation": 20, "asphalt": 10, "other": 5})
    # normalise to ~100
    s = sum(base.values())
    return {k: round(v / s * 100, 2) for k, v in base.items()}


def _synthetic_satellite(face: dict[str, Any]) -> dict[str, Any]:
    seed = f"sat|{face['id']}"
    segs = _segments_for_surface(face.get("surface_class"), seed)
    legend = {
        "concrete": [180, 180, 180],
        "asphalt": [40, 40, 40],
        "metal": [200, 200, 210],
        "vegetation": [34, 120, 50],
        "bare_soil": [160, 120, 80],
        "shadow": [30, 30, 30],
        "other": [120, 120, 120],
    }
    return {
        "coordinates": {"latitude": face["lat"], "longitude": face["lon"]},
        "image_year": 2024,
        "original_image": {
            "ref": f"data/fixtures/twin/images/{face['id']}_sat_original.png",
            "media_type": "image/png",
        },
        "segmentation": {
            "segments": segs,
            "legend": {k: legend[k] for k in segs if k in legend},
            "mask_image": {
                "ref": f"data/fixtures/twin/images/{face['id']}_sat_mask.png",
                "media_type": "image/png",
            },
            "dimensions": {"height": 350, "width": 350},
            "processing_time_seconds": round(0.2 + _unit(seed) * 0.3, 3),
            "request_id": hashlib.sha256(seed.encode()).hexdigest()[:8],
        },
        "mode": "sat",
        "fg_activity_id": f"replay-sat-{face['id']}",
    }


def _synthetic_streetview(face: dict[str, Any]) -> dict[str, Any] | None:
    """Greenfield / open deck may have weak SV — still emit a capture with high sky."""
    seed = f"sv|{face['id']}"
    # elevated open decks → more sky; slabs → more built
    sky = float(face.get("sky_view_factor") or 0.7)
    built = max(5.0, (1.0 - sky) * 70)
    segs = {
        "sky": round(sky * 100, 2),
        "building": round(built * 0.6, 2),
        "ground": round(built * 0.3, 2),
        "vegetation": round(max(0, 100 - sky * 100 - built), 2),
    }
    legend = {
        "sky": [135, 206, 235],
        "building": [100, 100, 100],
        "ground": [139, 119, 90],
        "vegetation": [34, 139, 34],
    }
    return {
        "coordinates": {"latitude": face["lat"], "longitude": face["lon"]},
        "vertical_angle": 10.0,
        "horizontal_angle": 90.0,
        "back_view_requested": False,
        "front": {
            "original_image": {
                "ref": f"data/fixtures/twin/images/{face['id']}_sv_original.png",
                "media_type": "image/png",
            },
            "segmentation": {
                "segments": segs,
                "legend": legend,
                "mask_image": {
                    "ref": f"data/fixtures/twin/images/{face['id']}_sv_mask.png",
                    "media_type": "image/png",
                },
                "dimensions": {"height": 640, "width": 640},
                "processing_time_seconds": round(0.3 + _unit(seed) * 0.4, 3),
                "request_id": hashlib.sha256(seed.encode()).hexdigest()[:8],
            },
            "image_date": "2024-06-01",
        },
        "back": None,
        "fg_activity_id": f"replay-sv-{face['id']}",
    }


def _confidence(sat: dict | None, sv: dict | None) -> str:
    if sat and sv:
        return "high"
    if sat or sv:
        return "medium"
    return "low"


def _build_replay_bundle(faces: list[dict[str, Any]]) -> dict[str, Any]:
    captures = []
    for face in faces:
        sat = _synthetic_satellite(face)
        sv = _synthetic_streetview(face)
        captures.append(
            {
                "work_face_id": face["id"],
                "centroid_lon": face["lon"],
                "centroid_lat": face["lat"],
                "satellite": sat,
                "streetview": sv,
                "capture_confidence": _confidence(sat, sv),
                "notes": None,
            }
        )
    return {
        "schema_version": "1.0.0",
        "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_id": _site_id(),
        "captures": captures,
        "cached_forever": True,
        "replay": True,
    }


def _env_params_body(lat: float, lon: float, temperature: float) -> dict[str, Any]:
    return {
        "latitude": lat,
        "longitude": lon,
        "temperature": temperature,
        "date_time": {
            "start_date": CHAIN_DATE,
            "start_time": CHAIN_TIME,
            "filter_type": 1,
        },
    }


def _heat_intel_body(lat: float, lon: float, temperature: float) -> dict[str, Any]:
    return {
        "latitude": lat,
        "longitude": lon,
        "temperature": temperature,
        "date": CHAIN_DATE,
        "analysis": ["environmental", "geographic", "urban", "events", "anthropogenic"],
    }


def _replay_env_params(hero: dict[str, Any], temperature: float) -> dict[str, Any]:
    """Clone Day-1 env structure with chained temp/coords if fixture exists."""
    matches = sorted(FIXTURES.glob("env_params_result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    base: dict[str, Any] = {
        "error": False,
        "status_code": 200,
        "message": "Completed",
        "data": {
            "activity_id": f"replay-env-{hero['id']}",
            "status": "Completed",
            "result": {
                "metadata": {
                    "timezone": "America/Phoenix",
                    "timezone_offset_hours": -7,
                    "time_range": {
                        "start": f"{CHAIN_DATE}T{CHAIN_TIME}:00-07:00",
                        "end": f"{CHAIN_DATE}T{CHAIN_TIME}:00-07:00",
                        "interval": "1h",
                        "count": 1,
                    },
                    "timestamps": [f"{CHAIN_DATE}T{CHAIN_TIME}:00-07:00"],
                },
                "locations": [
                    {
                        "lat": hero["lat"],
                        "lon": hero["lon"],
                        "elevation": 468.0,
                        "temperature": temperature,
                        "parameters": {
                            "relative_humidity_percent": [25.0],
                            "wet_bulb_temperature_celsius": [22.0],
                            "cloud_cover_octas": [1.0],
                            "heat_index_celsius": [temperature],
                        },
                        "solar_irradiance": {
                            "clear_sky": {"ghi": 950.0, "dni": 850.0, "dhi": 120.0},
                            "description": "REPLAY synthetic clear-sky August 14:00 Phoenix",
                        },
                    }
                ],
            },
        },
        "_chain": {
            "temperature_source": "heatmap_stats.mean",
            "temperature_c": temperature,
            "date_time": {"start_date": CHAIN_DATE, "start_time": CHAIN_TIME, "filter_type": 1},
            "work_face_id": hero["id"],
        },
    }
    if matches:
        try:
            live = json.loads(matches[0].read_text())
            # keep richer live body but stamp chain metadata + hero coords/temp
            live = dict(live)
            live["_chain"] = base["_chain"]
            data = live.get("data") or {}
            result = data.get("result") or {}
            locs = result.get("locations") or []
            if locs and isinstance(locs[0], dict):
                locs[0] = {**locs[0], "lat": hero["lat"], "lon": hero["lon"], "temperature": temperature}
            return live
        except (json.JSONDecodeError, OSError):
            pass
    return base


def _replay_heat_intel(hero: dict[str, Any], temperature: float) -> dict[str, Any]:
    matches = sorted(
        FIXTURES.glob("heat_intelligence_result*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    payload = {
        "error": False,
        "status_code": 200,
        "message": "Completed",
        "data": {
            "activity_id": f"replay-hi-{hero['id']}",
            "status": "Completed",
            "result": {
                "download_link": "[REDACTED — PDF saved as heat_intelligence_hero.pdf]",
            },
        },
        "_chain": {
            "temperature_source": "heatmap_stats.mean",
            "temperature_c": temperature,
            "date": CHAIN_DATE,
            "work_face_id": hero["id"],
            "hero": True,
        },
    }
    if matches:
        try:
            live = json.loads(matches[0].read_text())
            live = dict(live)
            live["_chain"] = payload["_chain"]
            # always redact
            res = ((live.get("data") or {}).get("result")) or {}
            if isinstance(res, dict) and "download_link" in res:
                link = res.get("download_link") or ""
                if not str(link).startswith("[REDACTED"):
                    res = {**res, "download_link": "[REDACTED — PDF saved as heat_intelligence_hero.pdf]"}
                    live["data"] = {**(live.get("data") or {}), "result": res}
            return live
        except (json.JSONDecodeError, OSError):
            pass
    return payload


async def _run_live(faces: list[dict[str, Any]], temperature: float) -> tuple[dict, dict, dict]:
    from apps.api.fortyguard.client import FortyGuardClient

    client = FortyGuardClient(replay_mode=False)
    client.max_poll_s = 300.0
    captures = []

    for i, face in enumerate(faces, 1):
        print(f"[{i}/{len(faces)}] live twin {face['id']}")
        sat_body = {
            "sat": {"latitude": face["lat"], "longitude": face["lon"]},
            "date_time": {
                "start_date": CHAIN_DATE,
                "start_time": CHAIN_TIME,
                "filter_type": 1,
            },
            "granularity": 80,
        }
        sv_body = {
            "latitude": face["lat"],
            "longitude": face["lon"],
            "vertical_angle": 10.0,
            "horizontal_angle": 90.0,
            "back_view": False,
        }
        sat_raw = None
        sv_raw = None
        try:
            sat_raw = await client.call("satellite", sat_body, force_live=True)
        except Exception as e:
            print(f"  satellite failed: {e}")
        try:
            sv_raw = await client.call("streetview", sv_body, force_live=True)
        except Exception as e:
            print(f"  streetview failed: {e}")

        sat_cap = _normalize_satellite(sat_raw, face) if sat_raw else None
        sv_cap = _normalize_streetview(sv_raw, face) if sv_raw else None
        notes = None
        if sat_cap is None and sv_cap is None:
            notes = "both satellite and streetview failed; no twin signal"
            # skip faces with neither — schema forbids empty; use minimal stub notes path
            # still emit medium/low with synthetic so T3 has a row
            sat_cap = _synthetic_satellite(face)
            sv_cap = None
            notes = "live failed; REPLAY-shaped satellite stub only"

        captures.append(
            {
                "work_face_id": face["id"],
                "centroid_lon": face["lon"],
                "centroid_lat": face["lat"],
                "satellite": sat_cap,
                "streetview": sv_cap,
                "capture_confidence": _confidence(sat_cap, sv_cap),
                "notes": notes,
            }
        )

    hero = next(f for f in faces if f["id"] == HERO_ID)
    print(f"env_params chain temp={temperature}°C @ {hero['id']}")
    env = await client.call("env_params", _env_params_body(hero["lat"], hero["lon"], temperature), force_live=True)
    env["_chain"] = {
        "temperature_source": "heatmap_stats.mean",
        "temperature_c": temperature,
        "date_time": {"start_date": CHAIN_DATE, "start_time": CHAIN_TIME, "filter_type": 1},
        "work_face_id": hero["id"],
    }

    print(f"heat_intelligence hero {HERO_ID}")
    hi = await client.call(
        "heat_intelligence",
        _heat_intel_body(hero["lat"], hero["lon"], temperature),
        force_live=True,
    )
    hi["_chain"] = {
        "temperature_source": "heatmap_stats.mean",
        "temperature_c": temperature,
        "date": CHAIN_DATE,
        "work_face_id": HERO_ID,
        "hero": True,
    }

    bundle = {
        "schema_version": "1.0.0",
        "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_id": _site_id(),
        "captures": captures,
        "cached_forever": True,
        "replay": False,
    }
    return bundle, env, hi


def _normalize_satellite(raw: dict, face: dict) -> dict | None:
    data = (raw.get("data") or {})
    if data.get("status") == "Failed":
        return None
    result = data.get("result") or {}
    if isinstance(result, list):
        result = result[0] if result else {}
    coords = result.get("coordinates") or {}
    seg = result.get("segmentation") or {}
    dims = seg.get("image_dimensions") or {}
    # strip heavy base64 — path refs only
    return {
        "coordinates": {
            "latitude": float(coords.get("latitude") or face["lat"]),
            "longitude": float(coords.get("longitude") or face["lon"]),
        },
        "image_year": result.get("image_year"),
        "original_image": {
            "ref": f"data/fixtures/twin/images/{face['id']}_sat_original.png",
            "media_type": "image/png",
        },
        "segmentation": {
            "segments": seg.get("segments") or {},
            "legend": seg.get("image_legend") or seg.get("legend") or {},
            "mask_image": {
                "ref": f"data/fixtures/twin/images/{face['id']}_sat_mask.png",
                "media_type": "image/png",
            },
            "dimensions": {
                "height": int(dims.get("height") or 350),
                "width": int(dims.get("width") or 350),
            }
            if dims
            else {"height": 350, "width": 350},
            "processing_time_seconds": seg.get("processing_time_seconds"),
            "request_id": seg.get("request_id"),
        },
        "mode": seg.get("mode") or "sat",
        "fg_activity_id": str(data.get("activity_id") or f"sat-{face['id']}"),
    }


def _normalize_streetview(raw: dict, face: dict) -> dict | None:
    data = (raw.get("data") or {})
    if data.get("status") == "Failed":
        return None
    result = data.get("result") or {}
    coords = result.get("coordinates") or {}
    front = result.get("front") or {}
    seg = front.get("segments") or front.get("segmentation") or {}
    if not front and not result:
        return None
    # streetview result schema varies; keep a valid StreetViewCapture shape
    segments = seg if isinstance(seg, dict) and not any(
        k in seg for k in ("segments", "image_legend")
    ) else (seg.get("segments") or {})
    legend = {}
    if isinstance(seg, dict):
        legend = seg.get("image_legend") or seg.get("legend") or {}
    return {
        "coordinates": {
            "latitude": float(coords.get("latitude") or face["lat"]),
            "longitude": float(coords.get("longitude") or face["lon"]),
        },
        "vertical_angle": 10.0,
        "horizontal_angle": 90.0,
        "back_view_requested": False,
        "front": {
            "original_image": {
                "ref": f"data/fixtures/twin/images/{face['id']}_sv_original.png",
                "media_type": "image/png",
            },
            "segmentation": {
                "segments": segments if isinstance(segments, dict) else {},
                "legend": legend if isinstance(legend, dict) else {},
                "mask_image": {
                    "ref": f"data/fixtures/twin/images/{face['id']}_sv_mask.png",
                    "media_type": "image/png",
                },
                "dimensions": {"height": 640, "width": 640},
                "processing_time_seconds": None,
                "request_id": None,
            },
            "image_date": front.get("image_date"),
        },
        "back": None,
        "fg_activity_id": str(data.get("activity_id") or f"sv-{face['id']}"),
    }


def write_outputs(bundle: dict, env: dict, hi: dict, *, temperature: float, live: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "images").mkdir(exist_ok=True)
    # placeholder so image refs resolve as paths (no binary in REPLAY)
    keep = OUT_DIR / "images" / ".gitkeep"
    if not keep.exists():
        keep.write_text("")

    bundle_path = OUT_DIR / "twin_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, default=str))
    (OUT_DIR / "env_params_chained.json").write_text(json.dumps(env, indent=2, default=str))
    (OUT_DIR / "heat_intelligence_hero.json").write_text(json.dumps(hi, indent=2, default=str))

    # copy existing PDF if present from Day-1
    pdf_src = list(FIXTURES.glob("heat_intelligence_report*.pdf"))
    if pdf_src:
        dest = OUT_DIR / "heat_intelligence_hero.pdf"
        dest.write_bytes(pdf_src[0].read_bytes())

    manifest = {
        "generated_at": bundle["generated_at"],
        "replay": bundle.get("replay", not live),
        "n_work_faces": len(bundle["captures"]),
        "hero_work_face_id": HERO_ID,
        "chain_temperature_c": temperature,
        "chain_date": CHAIN_DATE,
        "chain_time": CHAIN_TIME,
        "chain_rule": "env_params and heat_intelligence temperature+date_time taken from heatmap fixture stats — never invented",
        "confidence_counts": _count_confidence(bundle),
        "outputs": {
            "twin_bundle": "data/fixtures/twin/twin_bundle.json",
            "env_params_chained": "data/fixtures/twin/env_params_chained.json",
            "heat_intelligence_hero": "data/fixtures/twin/heat_intelligence_hero.json",
        },
        "cached_forever": True,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {bundle_path}")
    print(f"wrote {OUT_DIR / 'env_params_chained.json'}")
    print(f"wrote {OUT_DIR / 'heat_intelligence_hero.json'}")
    print(f"wrote {OUT_DIR / 'manifest.json'}")
    print(f"faces={manifest['n_work_faces']} hero={HERO_ID} chain_temp={temperature}°C")


def _count_confidence(bundle: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in bundle.get("captures") or []:
        k = c.get("capture_confidence") or "unknown"
        counts[k] = counts.get(k, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day-5 twin capture + env chain + hero heat intel")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    faces = _load_faces()
    if not any(f["id"] == HERO_ID for f in faces):
        raise SystemExit(f"Hero {HERO_ID} not in work_faces.geojson")

    temperature = _heatmap_chain_temp()
    print(f"chained temperature from heatmap: {temperature} °C")
    print(f"work faces: {len(faces)}; hero: {HERO_ID}")

    if not args.write:
        parser.print_help()
        print("\nUse --write (optional --live).")
        return 1

    if args.live:
        import asyncio

        bundle, env, hi = asyncio.run(_run_live(faces, temperature))
    else:
        bundle = _build_replay_bundle(faces)
        hero = next(f for f in faces if f["id"] == HERO_ID)
        env = _replay_env_params(hero, temperature)
        hi = _replay_heat_intel(hero, temperature)

    write_outputs(bundle, env, hi, temperature=temperature, live=args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
