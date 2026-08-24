"""Day-9 fixture completeness pass — every demo path has a committed response.

    python -m scripts.check_fixtures
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED = [
    # Day 1–2 FG
    "data/fixtures/heatmap_result_20260822_085533.json",
    "data/fixtures/env_params_result_20260822_085533.json",
    # Day 3–4
    "data/aoi/tile_clusters.geojson",
    "data/aoi/plan.json",
    "data/fixtures/historical/sweep_bundle.json",
    "data/fixtures/historical/manifest.json",
    "data/fixtures/wind_open_meteo.json",
    # Day 5 twin
    "data/fixtures/twin/twin_bundle.json",
    "data/fixtures/twin/env_params_chained.json",
    "data/fixtures/twin/heat_intelligence_hero.json",
    # Day 6 schedule
    "data/project_demo/schedule_export.csv",
    "data/project_demo/activities.json",
    # Day 7 site systems
    "data/mitigations/catalog.json",
    "data/fixtures/site_systems.json",
    # Day 8 agent / record
    "data/fixtures/agent_run_live.json",
    "data/fixtures/record_chain_live.json",
    "data/fixtures/agent_run_summary.json",
    # Day 9 january + exports checked separately if present
    "data/fixtures/historical/january_cold_manifest.json",
]


def main() -> int:
    missing = []
    present = []
    for rel in REQUIRED:
        p = REPO / rel
        if p.exists():
            present.append(rel)
        else:
            missing.append(rel)

    print(f"fixture completeness: {len(present)}/{len(REQUIRED)} required paths present")
    for m in missing:
        print(f"  MISSING  {m}")
    if not missing:
        print("  all required demo fixtures committed on disk")
    # exports optional until certificate is run
    exports = list((REPO / "data" / "exports").glob("certificate_*.pdf")) if (REPO / "data" / "exports").exists() else []
    print(f"certificates on disk: {len(exports)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
