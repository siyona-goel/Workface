-- WORKFACE — climatology_prior provenance columns.  T3, Day 5.
--
-- Additive, non-breaking (ADD COLUMN IF NOT EXISTS): gives the two fields the
-- Day-5 brief (WORKFACE_T3_DAY56 §A2 / §2.3) mandates be carried on EVERY prior
-- row a home in Postgres, alongside the core columns from 001_init.sql.
--
--   coverage           — how p_open was obtained:
--                        'observed'               (floor rate straight from counts)
--                        'modelled_hour'          (hot band placed on the diurnal)
--                        'insufficient_threshold' (threshold never swept -> p_open NULL)
--   hour_of_day_source — 'modelled' | 'observed' | 'none'. The brief: this label
--                        never gets dropped in a summary.
--
-- NOTE for T2/T1: this only touches climatology_prior, which is T3-owned. No
-- other table changes. `median_peak_c` stays as-is and is NULL on every row
-- (the sweep carries no temperature magnitude — see priors.py and the T2 ask to
-- populate TileReading.hourly_tcm_c on the next sweep).

ALTER TABLE climatology_prior
    ADD COLUMN IF NOT EXISTS coverage text
        CHECK (coverage IN ('observed', 'modelled_hour', 'insufficient_threshold'));

ALTER TABLE climatology_prior
    ADD COLUMN IF NOT EXISTS hour_of_day_source text
        CHECK (hour_of_day_source IN ('modelled', 'observed', 'none'));
