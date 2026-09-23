-- Read-only check after applying the AniList source migration.
-- Both checks must include anilist and be validated, with RLS still enabled.
select c.conrelid::regclass as table_name, c.conname, c.convalidated,
       pg_get_constraintdef(c.oid) as constraint_definition
from pg_constraint c
where c.conrelid in ('public.marquee_statuses'::regclass,
                     'public.marquee_ratings'::regclass)
  and c.conname in ('marquee_statuses_source_check', 'marquee_ratings_source_check')
order by c.conrelid::regclass::text;

select c.relname, c.relrowsecurity
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname in ('marquee_statuses', 'marquee_ratings')
order by c.relname;
