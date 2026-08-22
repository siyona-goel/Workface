-- OWNER: T2 — Day 3. Fill the tile_cluster stub + persist credit-meter readings.
-- Does not rewrite 001_init.sql (T3). Additive only.

ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS aoi_geom geometry(Polygon, 4326);
ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS h3_cells text[];
ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS work_face_ids text[];
ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS n_faces integer;
ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS granularity_plan_m integer;
ALTER TABLE tile_cluster ADD COLUMN IF NOT EXISTS granularity_commit_m integer;

-- Keep geom in sync with aoi_geom for readers of the Day-1 stub.
UPDATE tile_cluster SET aoi_geom = geom WHERE aoi_geom IS NULL AND geom IS NOT NULL;

CREATE TABLE IF NOT EXISTS credit_reading (
    id            bigserial PRIMARY KEY,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    remaining     bigint,
    used_estimated bigint,
    calls_today   integer,
    max_calls_per_day integer,
    source        text NOT NULL,
    raw           jsonb
);

CREATE INDEX IF NOT EXISTS idx_credit_reading_fetched ON credit_reading (fetched_at DESC);
