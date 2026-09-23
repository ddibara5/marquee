-- Read-only role check after application. Run as a privileged SQL editor role.
-- Set OWNER_ID to a real Marquee user and OTHER_ID to a different UUID in a
-- disposable test environment for row-level probes. Do not put those IDs in git.

select tablename,
       has_table_privilege('anon', format('public.%I', tablename), 'SELECT') as anon_can_select,
       has_table_privilege('anon', format('public.%I', tablename), 'INSERT') as anon_can_insert,
       has_table_privilege('authenticated', format('public.%I', tablename), 'SELECT') as auth_can_select,
       has_table_privilege('service_role', format('public.%I', tablename), 'INSERT') as service_can_insert
from pg_tables
where schemaname = 'public' and tablename like 'marquee\_%' escape '\'
order by tablename;

-- Every result for anon_can_select and anon_can_insert must be false.
-- Catalog and four directly editable owner tables have auth_can_select=true.
-- Operational tables and history source links have auth_can_select=false.
-- All service_can_insert must be true.

select tablename, cmd, qual, with_check from pg_policies
where schemaname = 'public' and tablename in
  ('marquee_watch_history', 'marquee_statuses', 'marquee_ratings', 'marquee_watchlist')
order by tablename, cmd;

-- In a disposable database with two fixture auth users, create one catalog
-- title and one user-state row per owner using service_role. Then, in separate
-- transactions for each test identity:
--
-- begin;
-- set local role authenticated;
-- select set_config('request.jwt.claim.sub', '<OWNER_ID>', true);
-- select count(*) from public.marquee_statuses where user_id = '<OWNER_ID>';
-- select count(*) from public.marquee_statuses where user_id = '<OTHER_ID>';
-- -- Expected: one own row, zero other rows.
-- rollback;
--
-- Repeat as OTHER_ID, including an attempted update changing user_id. Expect
-- zero visible owner rows and a denied cross-owner write. Confirm service_role
-- can insert a raw row and mapping with a stable ID, while anon cannot read.
