# Fixture freeze

Started: 2026-08-24T14:43:36.659452+00:00

Demo and GitHub Actions must run with `REPLAY_MODE=true`.
Do not re-fetch FortyGuard for these paths unless deliberately replacing a fixture.

| Path | On disk |
|------|---------|
| `data/fixtures/heatmap_result_20260822_085533.json` | yes |
| `data/fixtures/env_params_result_20260822_085533.json` | yes |
| `data/aoi/tile_clusters.geojson` | yes |
| `data/aoi/plan.json` | yes |
| `data/fixtures/historical/sweep_bundle.json` | yes |
| `data/fixtures/historical/january_cold_manifest.json` | yes |
| `data/fixtures/wind_open_meteo.json` | yes |
| `data/fixtures/twin/twin_bundle.json` | yes |
| `data/fixtures/twin/env_params_chained.json` | yes |
| `data/fixtures/twin/heat_intelligence_hero.json` | yes |
| `data/project_demo/activities.json` | yes |
| `data/project_demo/schedule_export.csv` | yes |
| `data/mitigations/catalog.json` | yes |
| `data/fixtures/site_systems.json` | yes |
| `data/fixtures/agent_run_live.json` | yes |
| `data/fixtures/record_chain_live.json` | yes |
| `data/fixtures/agent_run_summary.json` | yes |

Certificates: 1 PDF(s) under `data/exports/`.

## Day 10 checklist
- [ ] GitHub secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
- [ ] Actions → agent-cron → Run workflow (green)
- [ ] Supabase: new row in agent_run + record_entry count increased
- [ ] REPLAY_MODE=true in workflow (already set)

## Day 11
- [ ] Network off: `REPLAY_MODE=true python -m apps.api.agent.worker` still works
- [ ] No further fixture edits without team agreement

