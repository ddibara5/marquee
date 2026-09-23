-- Read-only. Capture result BEFORE and AFTER the Marquee migration and diff.
-- GameDeck rows, RLS, policies and grants must not change.

select c.relname as table_name, c.relrowsecurity as rls_enabled,
       c.relforcerowsecurity as force_rls, c.relacl::text as acl
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('games', 'play_events', 'game_ranks', 'rank_comparisons')
order by c.relname;

select tablename, policyname, cmd, roles, qual, with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('games', 'play_events', 'game_ranks', 'rank_comparisons')
order by tablename, policyname;

select 'games' as table_name, count(*) as rows from public.games
union all select 'play_events', count(*) from public.play_events
union all select 'game_ranks', count(*) from public.game_ranks
union all select 'rank_comparisons', count(*) from public.rank_comparisons
order by table_name;

-- Post-application only. Exactly 16 tables; no Marquee table lacks RLS.
select c.relname as table_name, c.relrowsecurity as rls_enabled,
       has_table_privilege('anon', c.oid, 'SELECT') as anon_select,
       has_table_privilege('authenticated', c.oid, 'SELECT') as signed_in_select,
       has_table_privilege('service_role', c.oid, 'INSERT') as service_insert
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') and c.relname like 'marquee\_%' escape '\'
order by c.relname;

select schemaname, tablename, policyname, cmd, roles, qual, with_check
from pg_policies where schemaname = 'public' and tablename like 'marquee\_%' escape '\'
order by tablename, policyname;

-- Security and performance advisors must also be checked by the applying operator.
