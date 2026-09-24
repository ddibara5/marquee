-- REVIEW DRAFT ONLY: do not execute or copy into supabase/migrations before approval.
-- New Marquee objects only. This preserves marquee_watch_history.watched_at NOT NULL.
-- The catalog/episode seed, replay adapter, progress union and status derivation are
-- separate reviewed work; these tables alone do not create any completions.

create table public.marquee_undated_completions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  episode_id uuid references public.marquee_episodes (id),
  movie_title_id uuid references public.marquee_movies (title_id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(episode_id, movie_title_id) = 1),
  unique (user_id, id)
);
create unique index marquee_undated_completions_episode_unique
  on public.marquee_undated_completions (user_id, episode_id)
  where episode_id is not null;
create unique index marquee_undated_completions_movie_unique
  on public.marquee_undated_completions (user_id, movie_title_id)
  where movie_title_id is not null;
create index marquee_undated_completions_episode_fk_idx
  on public.marquee_undated_completions (episode_id) where episode_id is not null;
create index marquee_undated_completions_movie_fk_idx
  on public.marquee_undated_completions (movie_title_id) where movie_title_id is not null;

create table public.marquee_undated_completion_evidence (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  completion_id uuid not null,
  raw_id uuid not null references public.marquee_ingest_raw (id) on delete cascade,
  source text not null check (source in ('crunchyroll', 'anilist')),
  source_episode_identifier text,
  created_at timestamptz not null default now(),
  foreign key (user_id, completion_id)
    references public.marquee_undated_completions (user_id, id) on delete cascade,
  unique (completion_id, raw_id),
  check (
    (source = 'crunchyroll' and source_episode_identifier is not null
      and btrim(source_episode_identifier) <> '') or
    (source = 'anilist' and source_episode_identifier is null)
  )
);
create index marquee_undated_evidence_completion_fk_idx
  on public.marquee_undated_completion_evidence (user_id, completion_id);
create index marquee_undated_evidence_raw_fk_idx
  on public.marquee_undated_completion_evidence (raw_id);
-- AniList's one fully completed media-list entry may support many episodes.
-- One Crunchyroll raw event may support exactly one canonical target.
create unique index marquee_undated_evidence_crunchyroll_raw_unique
  on public.marquee_undated_completion_evidence (raw_id)
  where source = 'crunchyroll';

-- Foreign keys alone cannot check a raw row's user, source, entity type or flag.
-- This invoker trigger runs only for service-role evidence writes.
create function public.marquee_guard_undated_evidence()
returns trigger language plpgsql set search_path = '' as $$
declare
  raw_owner uuid;
  raw_source text;
  raw_entity_type text;
  raw_payload jsonb;
begin
  select r.user_id, r.source, r.source_entity_type, r.payload
    into raw_owner, raw_source, raw_entity_type, raw_payload
    from public.marquee_ingest_raw r where r.id = new.raw_id;
  if not found or raw_owner is distinct from new.user_id
     or raw_source is distinct from new.source then
    raise exception 'Undated evidence raw source or owner mismatch';
  end if;
  if new.source = 'crunchyroll' then
    if raw_entity_type <> 'history_event'
       or raw_payload ->> 'fully_watched' is distinct from 'true'
       or raw_payload #>> '{panel,episode_metadata,identifier}'
          is distinct from new.source_episode_identifier then
      raise exception 'Invalid Crunchyroll completion evidence';
    end if;
  elsif new.source = 'anilist' then
    if raw_entity_type <> 'media_list'
       or raw_payload ->> 'status' is distinct from 'COMPLETED' then
      raise exception 'Invalid AniList completion evidence';
    end if;
    -- Replay separately verifies full progress, season identity and total.
  end if;
  return new;
end;
$$;
revoke all on function public.marquee_guard_undated_evidence()
  from public, anon, authenticated;
grant execute on function public.marquee_guard_undated_evidence()
  to service_role;
create trigger marquee_guard_undated_evidence_insert
  before insert on public.marquee_undated_completion_evidence
  for each row execute function public.marquee_guard_undated_evidence();

alter table public.marquee_undated_completions enable row level security;
alter table public.marquee_undated_completion_evidence enable row level security;
revoke all on table public.marquee_undated_completions,
  public.marquee_undated_completion_evidence from public, anon, authenticated;
grant select on table public.marquee_undated_completions to authenticated;
grant select, insert, update, delete on table
  public.marquee_undated_completions to service_role;
grant select, insert, delete on table
  public.marquee_undated_completion_evidence to service_role;
create policy marquee_undated_completions_read
  on public.marquee_undated_completions for select to authenticated
  using ((select auth.uid()) = user_id);
