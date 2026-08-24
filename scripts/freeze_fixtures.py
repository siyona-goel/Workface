"""Day 10–11: begin / complete fixture freeze.

Writes data/FIXTURE_FREEZE.md listing committed demo paths and sets
expectation that REPLAY_MODE=true is the only demo path.

    python -m scripts.freeze_fixtures
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "FIXTURE_FREEZE.md"

PATHS = [
    "data/fixtures/heatmap_result_20260822_085533.json",
    "data/fixtures/env_params_result_20260822_085533.json",
    "data/aoi/tile_clusters.geojson",
    "data/aoi/plan.json",
    "data/fixtures/historical/sweep_bundle.json",
    "data/fixtures/historical/january_cold_manifest.json",
    "data/fixtures/wind_open_meteo.json",
    "data/fixtures/twin/twin_bundle.json",
    "data/fixtures/twin/env_params_chained.json",
    "data/fixtures/twin/heat_intelligence_hero.json",
    "data/project_demo/activities.json",
    "data/project_demo/schedule_export.csv",
    "data/mitigations/catalog.json",
    "data/fixtures/site_systems.json",
    "data/fixtures/agent_run_live.json",
    "data/fixtures/record_chain_live.json",
    "data/fixtures/agent_run_summary.json",
]


def main() -> int:
    lines = [
        "# Fixture freeze",
        "",
        f"Started: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Demo and GitHub Actions must run with `REPLAY_MODE=true`.",
        "Do not re-fetch FortyGuard for these paths unless deliberately replacing a fixture.",
        "",
        "| Path | On disk |",
        "|------|---------|",
    ]
    missing = 0
    for rel in PATHS:
        ok = (REPO / rel).exists()
        if not ok:
            missing += 1
        lines.append(f"| `{rel}` | {'yes' if ok else '**MISSING**'} |")

    exports = sorted((REPO / "data" / "exports").glob("certificate_*.pdf")) if (REPO / "data" / "exports").exists() else []
    lines += [
        "",
        f"Certificates: {len(exports)} PDF(s) under `data/exports/`.",
        "",
        "## Day 10 checklist",
        "- [ ] GitHub secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY",
        "- [ ] Actions → agent-cron → Run workflow (green)",
        "- [ ] Supabase: new row in agent_run + record_entry count increased",
        "- [ ] REPLAY_MODE=true in workflow (already set)",
        "",
        "## Day 11",
        "- [ ] Network off: `REPLAY_MODE=true python -m apps.api.agent.worker` still works",
        "- [ ] No further fixture edits without team agreement",
        "",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(PATHS) - missing}/{len(PATHS)} paths present)")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
