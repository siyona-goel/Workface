"""AOI clustering — 40 work faces → 3–5 heatmap polygons.

Never one FortyGuard call per activity or per work face. Snap faces to their
parent structure, then greedily merge nearby structures until we are inside
the budget cap. FAB2 (hero deck) and ROAD (linear asphalt) stay unmerged so
a bbox merge cannot swallow empty acres of tiles.

    python -m apps.api.fortyguard.aoi --write

Writes:
  data/aoi/tile_clusters.geojson   polygons + metadata (T2-owned)
  data/aoi/plan.json               projected daily / sweep call counts (the Day-3 gate)
  data/aoi/assignments.json        work_face_id → tile_cluster_id
and stamps `tile_cluster_id` onto T3's work_faces.geojson + activities.json.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[3]
WORK_FACES = REPO / "data" / "project_demo" / "work_faces.geojson"
ACTIVITIES = REPO / "data" / "project_demo" / "activities.json"
BUDGET_PATH = REPO / "config" / "budget.yaml"
AOI_DIR = REPO / "data" / "aoi"

# ~N. Phoenix. Equirectangular is fine over a 2.4 km parcel.
_M_PER_DEG_LAT = 111_320.0

# Do not merge these into a neighbour even if they sit close: FAB2 is the hero
# 60 m cluster; ROAD is a long thin asphalt strip whose bbox would balloon.
_PROTECT = frozenset({"FAB2", "ROAD"})


def _m_per_deg_lon(lat: float) -> float:
    return _M_PER_DEG_LAT * math.cos(math.radians(lat))


def _load_budget(path: Path = BUDGET_PATH) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Tiny subset so tests still run if PyYAML isn't installed yet."""
    out: dict[str, Any] = {}
    current_map: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if current_map and line.startswith("  ") and ":" in line:
            k, v = line.strip().split(":", 1)
            out[current_map][k.strip()] = _coerce(v.strip())
            continue
        current_map = None
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key, val = k.strip(), v.strip()
        if val == "":
            out[key] = {}
            current_map = key
        else:
            out[key] = _coerce(val)
    return out


def _coerce(val: str) -> Any:
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_coerce(p.strip()) for p in inner.split(",")]
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val.strip("'\"")


def _ring(geom: dict) -> list[list[float]]:
    if geom.get("type") == "Polygon":
        return geom["coordinates"][0]
    raise ValueError(f"expected Polygon, got {geom.get('type')}")


def _bbox(ring: Iterable[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _union_bbox(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _pad_bbox(
    bbox: tuple[float, float, float, float],
    buffer_m: float,
    lat: float,
) -> tuple[float, float, float, float]:
    dlon = buffer_m / _m_per_deg_lon(lat)
    dlat = buffer_m / _M_PER_DEG_LAT
    west, south, east, north = bbox
    return west - dlon, south - dlat, east + dlon, north + dlat


def _bbox_polygon(bbox: tuple[float, float, float, float]) -> dict:
    west, south, east, north = bbox
    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _span_m(bbox: tuple[float, float, float, float], lat: float) -> tuple[float, float]:
    west, south, east, north = bbox
    return (
        abs(east - west) * _m_per_deg_lon(lat),
        abs(north - south) * _M_PER_DEG_LAT,
    )


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    west, south, east, north = bbox
    return (west + east) / 2, (south + north) / 2


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _est_tiles(bbox: tuple[float, float, float, float], lat: float, gran_m: int) -> int:
    w, h = _span_m(bbox, lat)
    return max(1, math.ceil(w / gran_m) * math.ceil(h / gran_m))


@dataclass
class Cluster:
    id: str
    name: str
    structure_ids: list[str]
    work_face_ids: list[str] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    granularity_plan_m: int = 100
    granularity_commit_m: int = 100

    def padded_polygon(self, buffer_m: float, lat: float) -> dict:
        return _bbox_polygon(_pad_bbox(self.bbox, buffer_m, lat))

    def to_feature(self, buffer_m: float, lat: float) -> dict:
        geom = self.padded_polygon(buffer_m, lat)
        padded = _pad_bbox(self.bbox, buffer_m, lat)
        w, h = _span_m(padded, lat)
        return {
            "type": "Feature",
            "properties": {
                "id": self.id,
                "name": self.name,
                "structure_ids": self.structure_ids,
                "work_face_ids": self.work_face_ids,
                "n_faces": len(self.work_face_ids),
                "granularity_plan_m": self.granularity_plan_m,
                "granularity_commit_m": self.granularity_commit_m,
                "width_m": round(w, 1),
                "height_m": round(h, 1),
                "est_tiles_plan": _est_tiles(padded, lat, self.granularity_plan_m),
                "est_tiles_commit": _est_tiles(padded, lat, self.granularity_commit_m),
            },
            "geometry": geom,
        }

    def polygon_aoi(self, buffer_m: float, lat: float) -> dict:
        """FortyGuard heatmap `polygon_aoi` FeatureCollection."""
        feat = self.to_feature(buffer_m, lat)
        feat["properties"] = {"name": self.id}
        return {"type": "FeatureCollection", "features": [feat]}


def load_work_faces(path: Path = WORK_FACES) -> list[dict]:
    fc = json.loads(path.read_text(encoding="utf-8"))
    return fc["features"]


def _structure_groups(faces: list[dict]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for feat in faces:
        props = feat["properties"]
        sid = props["structure_id"]
        ring = _ring(feat["geometry"])
        bb = _bbox(ring)
        if sid not in groups:
            groups[sid] = {
                "structure_id": sid,
                "bbox": bb,
                "work_face_ids": [props["id"]],
            }
        else:
            g = groups[sid]
            g["bbox"] = _union_bbox(g["bbox"], bb)
            g["work_face_ids"].append(props["id"])
    return groups


def _cluster_name(structure_ids: list[str]) -> tuple[str, str]:
    sids = set(structure_ids)
    if sids == {"FAB2"}:
        return "AOI-FAB2", "Fab 2 process module (hero 60 m cluster)"
    if sids == {"ROAD"}:
        return "AOI-ROAD", "Perimeter haul road"
    if sids == {"PARK"}:
        return "AOI-PARK", "Employee parking structure"
    if sids <= {"CUB", "CT", "SUB", "BULK"}:
        return "AOI-UTIL", "Central utilities / yards (CUB, CT, SUB, BULK)"
    if sids <= {"WHSE", "CHEM", "ADMIN", "PARK"}:
        return "AOI-SOUTH", "South campus support buildings"
    slug = "-".join(sorted(structure_ids))
    return f"AOI-{slug}", f"Cluster {slug}"


def cluster_work_faces(
    faces: list[dict] | None = None,
    *,
    max_polygons: int | None = None,
    budget: dict[str, Any] | None = None,
) -> list[Cluster]:
    """Greedy merge of structure bboxes → 3–5 AOI polygons."""
    budget = budget or _load_budget()
    faces = faces if faces is not None else load_work_faces()
    cap = max_polygons or int(budget.get("max_aoi_polygons", 5))
    plan_g = int(budget.get("granularity_plan_m", 100))
    commit_g = int(budget.get("granularity_commit_m", 60))

    groups = _structure_groups(faces)
    clusters: list[Cluster] = []
    for sid, g in groups.items():
        cid, name = _cluster_name([sid])
        clusters.append(
            Cluster(
                id=cid,
                name=name,
                structure_ids=[sid],
                work_face_ids=list(g["work_face_ids"]),
                bbox=g["bbox"],
            )
        )

    lat = sum(f["properties"]["centroid_lat"] for f in faces) / len(faces)

    def can_merge(a: Cluster, b: Cluster) -> bool:
        if any(s in _PROTECT for s in a.structure_ids) or any(
            s in _PROTECT for s in b.structure_ids
        ):
            return False
        union = _union_bbox(a.bbox, b.bbox)
        w, h = _span_m(union, lat)
        # Keep clusters compact: a 1.1 km box is ~one campus neighbourhood.
        return max(w, h) <= 1100.0

    while len(clusters) > cap:
        best: tuple[float, int, int] | None = None
        for i, a in enumerate(clusters):
            for j, b in enumerate(clusters):
                if j <= i or not can_merge(a, b):
                    continue
                ca = _centroid(a.bbox)
                cb = _centroid(b.bbox)
                d = _haversine_m(ca[0], ca[1], cb[0], cb[1])
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            # Forced merge of the closest pair that isn't two protected clusters.
            for i, a in enumerate(clusters):
                for j, b in enumerate(clusters):
                    if j <= i:
                        continue
                    if set(a.structure_ids) <= _PROTECT and set(b.structure_ids) <= _PROTECT:
                        continue
                    ca, cb = _centroid(a.bbox), _centroid(b.bbox)
                    d = _haversine_m(ca[0], ca[1], cb[0], cb[1])
                    if best is None or d < best[0]:
                        best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        a, b = clusters[i], clusters[j]
        merged_sids = a.structure_ids + b.structure_ids
        cid, name = _cluster_name(merged_sids)
        merged = Cluster(
            id=cid,
            name=name,
            structure_ids=merged_sids,
            work_face_ids=a.work_face_ids + b.work_face_ids,
            bbox=_union_bbox(a.bbox, b.bbox),
        )
        clusters = [c for k, c in enumerate(clusters) if k not in (i, j)]
        clusters.append(merged)

    # Stable ids / names after the last merge, granularity by role.
    out: list[Cluster] = []
    used_ids: set[str] = set()
    for c in clusters:
        cid, name = _cluster_name(c.structure_ids)
        if cid in used_ids:
            cid = f"{cid}-{c.structure_ids[0]}"
        used_ids.add(cid)
        commit = commit_g if "FAB2" in c.structure_ids else plan_g
        out.append(
            Cluster(
                id=cid,
                name=name,
                structure_ids=sorted(c.structure_ids),
                work_face_ids=sorted(c.work_face_ids),
                bbox=c.bbox,
                granularity_plan_m=plan_g,
                granularity_commit_m=commit,
            )
        )
    out.sort(key=lambda c: (-len(c.work_face_ids), c.id))
    return out


def assignments(clusters: list[Cluster]) -> dict[str, str]:
    return {fid: c.id for c in clusters for fid in c.work_face_ids}


def project_call_budget(
    clusters: list[Cluster],
    *,
    budget: dict[str, Any] | None = None,
    n_faces: int = 40,
) -> dict[str, Any]:
    """The Day-3 gate: projected daily call count, written down."""
    budget = budget or _load_budget()
    n = len(clusters)
    years = list(budget.get("climatology_years") or list(range(2019, 2026)))
    analytics = int(budget.get("climatology_analytics_per_year", 4))
    sweep_clustered = len(years) * analytics * n
    sweep_naive = len(years) * analytics * n_faces

    # Daily commit loop: one tcm + one time_of_measure heatmap per AOI,
    # plus one env_params chained off the AOI centroid (not per face).
    daily_clustered = n * 3
    daily_naive = n_faces * 3  # one heatmap + tom + env_params per face

    return {
        "n_aoi_polygons": n,
        "max_aoi_polygons": int(budget.get("max_aoi_polygons", 5)),
        "n_work_faces": n_faces,
        "clusters": [
            {
                "id": c.id,
                "n_faces": len(c.work_face_ids),
                "structure_ids": c.structure_ids,
                "granularity_plan_m": c.granularity_plan_m,
                "granularity_commit_m": c.granularity_commit_m,
            }
            for c in clusters
        ],
        "daily_commit_calls": {
            "clustered": daily_clustered,
            "naive_per_face": daily_naive,
            "note": "heatmap tcm (filter_type 2) + time_of_measure (filter_type 3) + env_params, per AOI not per face.",
        },
        "climatology_sweep_calls_once": {
            "clustered": sweep_clustered,
            "naive_per_face": sweep_naive,
            "years": years,
            "analytics_per_year": analytics,
            "note": "filter_type 4, one August window per year. Cached forever. Not a daily cost.",
        },
        "max_fg_calls_per_day": int(budget.get("max_fg_calls_per_day", 120)),
        "fail_at_fraction": float(budget.get("fail_at_fraction", 0.8)),
        "headroom_vs_daily_cap": int(budget.get("max_fg_calls_per_day", 120)) - daily_clustered,
    }


def heatmap_body(
    cluster: Cluster,
    *,
    start_date: str,
    start_time: str = "00:00",
    filter_type: int = 2,
    granularity: int | None = None,
    analytic_type: str = "tcm",
    buffer_m: float | None = None,
    lat: float = 33.785,
    extra: dict | None = None,
) -> dict:
    budget = _load_budget()
    buf = budget.get("aoi_buffer_m", 90) if buffer_m is None else buffer_m
    gran = granularity if granularity is not None else cluster.granularity_commit_m
    body: dict[str, Any] = {
        "polygon_aoi": cluster.polygon_aoi(float(buf), lat),
        "date_time": {
            "start_date": start_date,
            "start_time": start_time,
            "filter_type": filter_type,
        },
        "granularity": gran,
        "analytic_type": analytic_type,
    }
    if extra:
        body.update(extra)
    return body


def stamp_tile_cluster_ids(
    mapping: dict[str, str],
    *,
    work_faces_path: Path = WORK_FACES,
    activities_path: Path = ACTIVITIES,
) -> None:
    """Write T2's Day-3 assignment onto T3's committed geometry (null → cluster id)."""
    fc = json.loads(work_faces_path.read_text(encoding="utf-8"))
    for feat in fc["features"]:
        fid = feat["properties"]["id"]
        if fid in mapping:
            feat["properties"]["tile_cluster_id"] = mapping[fid]
    work_faces_path.write_text(json.dumps(fc, indent=2) + "\n", encoding="utf-8")

    schedule = json.loads(activities_path.read_text(encoding="utf-8"))
    for face in schedule.get("work_faces", []):
        fid = face.get("id")
        if fid in mapping:
            face["tile_cluster_id"] = mapping[fid]
    activities_path.write_text(json.dumps(schedule, indent=2) + "\n", encoding="utf-8")


def write_artifacts(
    clusters: list[Cluster],
    *,
    aoi_dir: Path = AOI_DIR,
    stamp: bool = True,
) -> dict[str, Any]:
    budget = _load_budget()
    faces = load_work_faces()
    lat = sum(f["properties"]["centroid_lat"] for f in faces) / len(faces)
    buf = float(budget.get("aoi_buffer_m", 90))
    aoi_dir.mkdir(parents=True, exist_ok=True)

    fc = {
        "type": "FeatureCollection",
        "name": "workface_tile_clusters",
        "features": [c.to_feature(buf, lat) for c in clusters],
    }
    (aoi_dir / "tile_clusters.geojson").write_text(
        json.dumps(fc, indent=2) + "\n", encoding="utf-8"
    )

    mapping = assignments(clusters)
    (aoi_dir / "assignments.json").write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    plan = project_call_budget(clusters, budget=budget, n_faces=len(faces))
    plan["site_lat"] = round(lat, 6)
    plan["aoi_buffer_m"] = buf
    (aoi_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    if stamp:
        stamp_tile_cluster_ids(mapping)

    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cluster work faces into ≤5 AOI polygons.")
    parser.add_argument("--write", action="store_true", help="Write data/aoi/* and stamp tile_cluster_id.")
    parser.add_argument("--no-stamp", action="store_true", help="Do not mutate T3's geojson / activities.json.")
    args = parser.parse_args(argv)

    clusters = cluster_work_faces()
    plan = project_call_budget(clusters)
    print(f"{len(clusters)} AOI polygons (cap {plan['max_aoi_polygons']}):")
    for c in clusters:
        print(f"  {c.id:12}  faces={len(c.work_face_ids):2}  structures={c.structure_ids}")
    daily = plan["daily_commit_calls"]
    print(
        f"daily commit calls: {daily['clustered']} clustered  vs  "
        f"{daily['naive_per_face']} naive  (cap {plan['max_fg_calls_per_day']})"
    )
    sweep = plan["climatology_sweep_calls_once"]
    print(
        f"one-time Aug sweep: {sweep['clustered']} clustered  vs  "
        f"{sweep['naive_per_face']} naive"
    )
    if args.write:
        write_artifacts(clusters, stamp=not args.no_stamp)
        print(f"wrote {AOI_DIR.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
