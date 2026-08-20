-- PAKSH 3.5: add the axes column to public.outlets.
--
-- Restores the authoritative 3-axis editorial data (secular_authoritative,
-- market_orientation, incumbent_stance - each 0-100) already present for all
-- 124 curated outlets in sources.py, but never carried into Supabase because
-- migrate_to_supabase.py's _outlet_rows() didn't include it and the outlets
-- table was never given a column for it (see the PAKSH 3.4 audit).
--
-- Idempotent: IF NOT EXISTS means running this twice is a no-op the second
-- time. Purely additive - no existing column is altered, dropped, or
-- renamed, and no row is touched by this statement (population happens
-- separately, via the normal outlet upsert path in execute_migration.py,
-- immediately after this runs).
--
-- Naming follows this project's existing Supabase migration convention
-- (see supabase list_migrations: {timestamp}_{snake_case_name}, e.g.
-- "paksh_content_schema_v1").

ALTER TABLE public.outlets
  ADD COLUMN IF NOT EXISTS axes JSONB;
