-- WORKFACE — initial schema.  T3, TASK 6.  Postgres 16 + PostGIS.
--
-- Tables T3 owns (WORKFACE_TECH_SPEC.md §2), plus empty stubs for the three
-- tables T2 owns (tile_cluster, fg_activity, fg_cache) so T2 can fill them in a
-- later migration without a conflict here. T2-owned objects are marked OWNER: T2.
--
-- Two things are NOT optional:
--   1. record_entry is append-only and hash-chained (trigger blocks UPDATE/DELETE).
--   2. trade_window.citation / standard_ref / source_url / verify_status are NOT NULL
--      — the database makes an uncited registry row impossible, not just the tests.
--
-- WORKFACE NAMING RULE:
--   activity.id      = a scheduled construction task (P6 / the generator)
--   fg_activity.id   = a FortyGuard async job handle
-- They are different things and live in different tables. Never blur them.

CREATE EXTENSION IF NOT EXISTS postgis;


-- =========================================================================== --
-- T2-owned stubs (create empty so work_face/thermal_series can reference them).
-- =========================================================================== --

-- OWNER: T2 — AOI clusters (3-5 polygons the 40 work faces group into).
CREATE TABLE IF NOT EXISTS tile_cluster (
    id           text PRIMARY KEY,
    name         text,
    geom         geometry(Polygon, 4326),
    granularity_m integer,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- OWNER: T2 — FortyGuard async job handles. NOTE: fg_activity.id is a FortyGuard
-- job handle, NOT a schedule activity.id. See the naming rule above.
CREATE TABLE IF NOT EXISTS fg_activity (
    id           text PRIMARY KEY,
    analytic_type text,
    status       text,
    submitted_at timestamptz,
    completed_at timestamptz,
    request      jsonb,
    response     jsonb
);

-- OWNER: T2 — cache of FortyGuard responses keyed by request digest.
CREATE TABLE IF NOT EXISTS fg_cache (
    request_digest text PRIMARY KEY,
    payload      jsonb NOT NULL,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz
);


-- =========================================================================== --
-- T3-owned: the schedule + geography
-- =========================================================================== --

CREATE TABLE IF NOT EXISTS work_face (
    id              text PRIMARY KEY,
    name            text,
    structure_id    text,
    level           text,
    geom            geometry(Polygon, 4326),
    centroid        geography(Point, 4326),
    area_m2         double precision,
    elevation_m     double precision,
    height_agl_m    double precision,
    exposure_class  text,
    surface_class   text,
    sky_view_factor double precision,
    orientation_deg double precision,
    twin_json       jsonb,
    tile_cluster_id text REFERENCES tile_cluster (id)
);

CREATE TABLE IF NOT EXISTS activity (
    id                text PRIMARY KEY,
    wbs               text,
    name              text,
    trade_id          text,                 -- FK added after trade_window exists
    work_face_id      text REFERENCES work_face (id),
    structure_id      text,
    discipline        text,
    thermal_sensitive boolean NOT NULL DEFAULT false,
    planned_start     timestamptz,
    planned_finish    timestamptz,
    duration_h        double precision,
    total_float_d     double precision,
    free_float_d      double precision,
    is_critical       boolean NOT NULL DEFAULT false,
    is_near_critical  boolean NOT NULL DEFAULT false,
    milestone_date    timestamptz,
    milestone_name    text,
    hold_point        text,
    iwp_id            text,
    calendar_id       text
);

CREATE TABLE IF NOT EXISTS activity_pred (
    activity_id text NOT NULL REFERENCES activity (id),
    pred_id     text NOT NULL REFERENCES activity (id),
    link_type   text NOT NULL DEFAULT 'FS',
    lag_h       double precision NOT NULL DEFAULT 0,
    PRIMARY KEY (activity_id, pred_id)
);


-- =========================================================================== --
-- T3-owned: the registry (every row must be cited — enforced by NOT NULL)
-- =========================================================================== --

CREATE TABLE IF NOT EXISTS trade_window (
    trade_id         text PRIMARY KEY,
    spec             jsonb NOT NULL,
    citation         text NOT NULL,
    standard_ref     text NOT NULL,
    source_url       text NOT NULL,
    verify_status    text NOT NULL
        CHECK (verify_status IN ('primary', 'secondary', 'partial')),
    registry_version text,
    CONSTRAINT citation_is_real CHECK (char_length(btrim(citation)) > 20)
);

-- activity.trade_id references the registry once trade_window exists.
ALTER TABLE activity
    DROP CONSTRAINT IF EXISTS activity_trade_id_fkey;
ALTER TABLE activity
    ADD CONSTRAINT activity_trade_id_fkey
    FOREIGN KEY (trade_id) REFERENCES trade_window (trade_id);


-- =========================================================================== --
-- T3-owned: the thermal record and the window evaluations
-- =========================================================================== --

CREATE TABLE IF NOT EXISTS thermal_series (
    work_face_id text NOT NULL REFERENCES work_face (id),
    ts           timestamptz NOT NULL,
    t_air_c      double precision,
    t_surf_c     double precision,
    t_dew_c      double precision,
    rh_pct       double precision,
    wbgt_c       double precision,
    ghi          double precision,
    wind_ms      double precision,
    source       text,
    confidence   text,
    PRIMARY KEY (work_face_id, ts)
);

CREATE TABLE IF NOT EXISTS window_eval (
    activity_id       text NOT NULL REFERENCES activity (id),
    run_id            text NOT NULL,
    open_intervals    jsonb,
    binding_constraint jsonb,
    margin            jsonb,
    verdict           text,
    citation          text,
    usd_exposure      jsonb,
    confidence        text,
    PRIMARY KEY (activity_id, run_id)
);

CREATE TABLE IF NOT EXISTS climatology_prior (
    tile_id       text NOT NULL,
    trade_id      text NOT NULL,
    month         smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
    hour          smallint NOT NULL CHECK (hour BETWEEN 0 AND 23),
    p_open        double precision,
    median_peak_c double precision,
    n_years       integer,
    PRIMARY KEY (tile_id, trade_id, month, hour)
);


-- =========================================================================== --
-- T3-owned: the agent trace and the append-only, hash-chained record
-- =========================================================================== --

CREATE TABLE IF NOT EXISTS agent_run (
    id          text PRIMARY KEY,
    run_id      text,
    kind        text,
    status      text,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    summary     jsonb
);

CREATE TABLE IF NOT EXISTS agent_step (
    id         bigserial PRIMARY KEY,
    run_id     text NOT NULL REFERENCES agent_run (id),
    seq        integer NOT NULL,
    kind       text,
    input      jsonb,
    output     jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- The artifact a claims consultant buys. Append-only and hash-chained: an
-- append-only table you can quietly UPDATE is not evidence.
CREATE TABLE IF NOT EXISTS record_entry (
    seq        bigserial PRIMARY KEY,
    prev_hash  text,
    hash       text NOT NULL,
    payload    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION record_entry_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'record_entry is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS record_entry_no_mutate ON record_entry;
CREATE TRIGGER record_entry_no_mutate
    BEFORE UPDATE OR DELETE ON record_entry
    FOR EACH ROW EXECUTE FUNCTION record_entry_is_append_only();


-- =========================================================================== --
-- Indexes
-- =========================================================================== --

CREATE INDEX IF NOT EXISTS idx_activity_planned_start   ON activity (planned_start);
CREATE INDEX IF NOT EXISTS idx_activity_trade_thermal   ON activity (trade_id) WHERE thermal_sensitive;
CREATE INDEX IF NOT EXISTS idx_activity_work_face        ON activity (work_face_id);
CREATE INDEX IF NOT EXISTS idx_thermal_series_ts         ON thermal_series (ts);
CREATE INDEX IF NOT EXISTS idx_window_eval_run           ON window_eval (run_id);
CREATE INDEX IF NOT EXISTS idx_work_face_geom            ON work_face USING gist (geom);
