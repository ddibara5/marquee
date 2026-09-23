-- Marquee only. Authored 2026-09-23; do not apply as part of repo bootstrap.
-- Run against the shared GameDeck project only after preflight and review.
-- All statements target new public.marquee_* objects; no global privileges.

create table public.marquee_titles (
  id uuid primary key default gen_random_uuid(),
  media_type text not null check (media_type in ('show', 'movie')),
  display_title text not null check (btrim(display_title) <> ''),
  original_title text,
  is_anime boolean not null default false,
  release_year integer check (release_year between 1880 and 2200),
  synopsis text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, media_type)
);

create table public.marquee_shows (
  title_id uuid primary key,
  media_type text not null default 'show' check (media_type = 'show'),
  created_at timestamptz not null default now(),
  foreign key (title_id, media_type) references public.marquee_titles (id, media_type)
);

create table public.marquee_movies (
  title_id uuid primary key,
  media_type text not null default 'movie' check (media_type = 'movie'),
  runtime_minutes integer check (runtime_minutes > 0),
  created_at timestamptz not null default now(),
  foreign key (title_id, media_type) references public.marquee_titles (id, media_type)
);

create table public.marquee_seasons (
  id uuid primary key default gen_random_uuid(),
  show_title_id uuid not null references public.marquee_shows (title_id),
  season_number integer check (season_number >= 0),
  display_title text,
  release_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index marquee_seasons_show_idx on public.marquee_seasons (show_title_id);
create unique index marquee_seasons_number_unique on public.marquee_seasons (show_title_id, season_number)
  where season_number is not null;

create table public.marquee_episodes (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null references public.marquee_seasons (id),
  episode_number integer check (episode_number > 0),
  absolute_number integer check (absolute_number > 0),
  display_title text,
  aired_at timestamptz,
  runtime_minutes integer check (runtime_minutes > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index marquee_episodes_season_idx on public.marquee_episodes (season_id);
create unique index marquee_episodes_number_unique on public.marquee_episodes (season_id, episode_number)
  where episode_number is not null;

create table public.marquee_watch_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  movie_title_id uuid references public.marquee_movies (title_id),
  episode_id uuid references public.marquee_episodes (id),
  logical_event_key text not null check (btrim(logical_event_key) <> ''),
  watched_at timestamptz not null,
  source text not null check (source in ('manual', 'trakt', 'crunchyroll')),
  source_record_id text,
  source_updated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(movie_title_id, episode_id) = 1),
  unique (user_id, id),
  unique (user_id, logical_event_key)
);
create index marquee_watch_history_movie_idx on public.marquee_watch_history (user_id, movie_title_id, watched_at desc);
create index marquee_watch_history_episode_idx on public.marquee_watch_history (user_id, episode_id, watched_at desc);

create table public.marquee_watch_history_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  history_id uuid not null,
  source text not null check (source in ('trakt', 'crunchyroll')),
  source_entity_type text not null,
  source_record_id text not null check (btrim(source_record_id) <> ''),
  observed_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (user_id, history_id) references public.marquee_watch_history (user_id, id) on delete cascade,
  unique (user_id, source, source_entity_type, source_record_id)
);
create index marquee_watch_history_sources_history_idx on public.marquee_watch_history_sources (history_id);

create table public.marquee_statuses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title_id uuid references public.marquee_titles (id),
  season_id uuid references public.marquee_seasons (id),
  status text not null check (status in ('planned', 'watching', 'completed', 'on_hold', 'dropped')),
  source text not null check (source in ('manual', 'trakt', 'crunchyroll', 'mal')),
  source_record_id text,
  source_updated_at timestamptz,
  manual_locked boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(title_id, season_id) = 1)
);
create unique index marquee_statuses_title_unique on public.marquee_statuses (user_id, title_id) where title_id is not null;
create unique index marquee_statuses_season_unique on public.marquee_statuses (user_id, season_id) where season_id is not null;

create table public.marquee_ratings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title_id uuid references public.marquee_titles (id),
  season_id uuid references public.marquee_seasons (id),
  score numeric(4,1) not null check (score >= 0 and score <= 10),
  source text not null check (source in ('manual', 'trakt', 'mal')),
  source_record_id text,
  source_updated_at timestamptz,
  manual_locked boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (num_nonnulls(title_id, season_id) = 1)
);
create unique index marquee_ratings_title_unique on public.marquee_ratings (user_id, title_id) where title_id is not null;
create unique index marquee_ratings_season_unique on public.marquee_ratings (user_id, season_id) where season_id is not null;

create table public.marquee_watchlist (
  user_id uuid not null references auth.users (id) on delete cascade,
  title_id uuid not null references public.marquee_titles (id),
  source text not null check (source in ('manual', 'trakt')),
  source_record_id text,
  source_updated_at timestamptz,
  manual_locked boolean not null default false,
  added_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, title_id)
);
create index marquee_watchlist_title_idx on public.marquee_watchlist (title_id);

-- Exactly one real canonical FK is populated. Provider IDs remain text.
create table public.marquee_source_mappings (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('trakt', 'crunchyroll', 'anilist', 'mal', 'tmdb', 'imdb')),
  source_entity_type text not null check (btrim(source_entity_type) <> ''),
  source_id text not null check (btrim(source_id) <> ''),
  canonical_entity_type text not null check (canonical_entity_type in ('title', 'show', 'movie', 'season', 'episode')),
  title_id uuid references public.marquee_titles (id),
  show_title_id uuid references public.marquee_shows (title_id),
  movie_title_id uuid references public.marquee_movies (title_id),
  season_id uuid references public.marquee_seasons (id),
  episode_id uuid references public.marquee_episodes (id),
  match_method text not null check (match_method in ('manual', 'external_id', 'rule')),
  rule_id text,
  confidence numeric(4,3) check (confidence between 0 and 1),
  manual_locked boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source, source_entity_type, source_id),
  check (num_nonnulls(title_id, show_title_id, movie_title_id, season_id, episode_id) = 1),
  check (
    (canonical_entity_type = 'title' and title_id is not null) or
    (canonical_entity_type = 'show' and show_title_id is not null) or
    (canonical_entity_type = 'movie' and movie_title_id is not null) or
    (canonical_entity_type = 'season' and season_id is not null) or
    (canonical_entity_type = 'episode' and episode_id is not null)
  )
);
create index marquee_source_mappings_title_idx on public.marquee_source_mappings (title_id) where title_id is not null;
create index marquee_source_mappings_show_idx on public.marquee_source_mappings (show_title_id) where show_title_id is not null;
create index marquee_source_mappings_movie_idx on public.marquee_source_mappings (movie_title_id) where movie_title_id is not null;
create index marquee_source_mappings_season_idx on public.marquee_source_mappings (season_id) where season_id is not null;
create index marquee_source_mappings_episode_idx on public.marquee_source_mappings (episode_id) where episode_id is not null;

create table public.marquee_franchise_overrides (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('anilist', 'mal', 'crunchyroll', 'trakt')),
  source_entity_type text not null,
  source_id text not null check (btrim(source_id) <> ''),
  show_title_id uuid not null references public.marquee_shows (title_id),
  reason text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source, source_entity_type, source_id)
);
create index marquee_franchise_overrides_show_idx on public.marquee_franchise_overrides (show_title_id);

create table public.marquee_mapping_review (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  source_entity_type text not null,
  source_id text not null check (btrim(source_id) <> ''),
  source_title text,
  candidates jsonb not null default '[]'::jsonb check (jsonb_typeof(candidates) = 'array'),
  reason text not null,
  status text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  resolved_mapping_id uuid references public.marquee_source_mappings (id),
  resolution_notes text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  check ((status = 'open' and resolved_at is null and resolved_mapping_id is null) or
         (status = 'resolved' and resolved_at is not null and resolved_mapping_id is not null) or
         (status = 'dismissed' and resolved_at is not null and resolved_mapping_id is null))
);
create unique index marquee_mapping_review_open_unique on public.marquee_mapping_review (source, source_entity_type, source_id)
  where status = 'open';
create index marquee_mapping_review_mapping_idx on public.marquee_mapping_review (resolved_mapping_id);

create table public.marquee_sync_runs (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('trakt', 'crunchyroll', 'anilist', 'mal', 'tmdb')),
  user_id uuid references auth.users (id) on delete cascade,
  scope_key text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  fetched_count integer not null default 0 check (fetched_count >= 0),
  inserted_count integer not null default 0 check (inserted_count >= 0),
  updated_count integer not null default 0 check (updated_count >= 0),
  skipped_count integer not null default 0 check (skipped_count >= 0),
  unmapped_count integer not null default 0 check (unmapped_count >= 0),
  error_count integer not null default 0 check (error_count >= 0),
  execution_id text,
  error_summary text,
  check ((user_id is null and scope_key = 'catalog') or (user_id is not null and scope_key = user_id::text)),
  check ((status = 'running' and finished_at is null) or
         (status in ('succeeded', 'failed') and finished_at is not null))
);
create index marquee_sync_runs_recent_idx on public.marquee_sync_runs (source, scope_key, started_at desc);

-- A row can move from running to one terminal outcome only. Ingestion has no
-- DELETE grant; auth.users deletion can still cascade for privacy.
create function public.marquee_guard_sync_runs() returns trigger
language plpgsql set search_path = '' as $$
begin
  if old.status <> 'running' or new.status = 'running' or
     (new.id, new.source, new.scope_key, new.started_at) is distinct from
     (old.id, old.source, old.scope_key, old.started_at) or
     new.user_id is distinct from old.user_id or
     new.execution_id is distinct from old.execution_id then
    raise exception 'marquee sync run can only transition once to a terminal outcome';
  end if;
  return new;
end;
$$;
revoke all on function public.marquee_guard_sync_runs() from public, anon, authenticated;
create trigger marquee_guard_sync_runs_trigger before update on public.marquee_sync_runs
  for each row execute function public.marquee_guard_sync_runs();

create table public.marquee_ingest_raw (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('trakt', 'crunchyroll', 'anilist', 'mal', 'tmdb')),
  source_entity_type text not null,
  source_id text,
  user_id uuid references auth.users (id) on delete cascade,
  scope_key text not null,
  dedupe_key text not null check (btrim(dedupe_key) <> ''),
  payload_hash text not null check (btrim(payload_hash) <> ''),
  payload jsonb not null,
  first_sync_run_id uuid references public.marquee_sync_runs (id),
  fetched_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  normalization_status text not null default 'pending'
    check (normalization_status in ('pending', 'mapped', 'review', 'ignored', 'error')),
  normalization_error text,
  check ((user_id is null and scope_key = 'catalog') or (user_id is not null and scope_key = user_id::text)),
  unique (scope_key, source, source_entity_type, dedupe_key)
);
create index marquee_ingest_raw_run_idx on public.marquee_ingest_raw (first_sync_run_id);
create index marquee_ingest_raw_pending_idx on public.marquee_ingest_raw (source, normalization_status, fetched_at)
  where normalization_status in ('pending', 'error', 'review');

create table public.marquee_sync_state (
  source text not null check (source in ('trakt', 'crunchyroll', 'anilist', 'mal', 'tmdb')),
  user_id uuid references auth.users (id) on delete cascade,
  scope_key text not null,
  watermark jsonb not null default '{}'::jsonb,
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  last_success_run_id uuid references public.marquee_sync_runs (id),
  updated_at timestamptz not null default now(),
  primary key (source, scope_key),
  check ((user_id is null and scope_key = 'catalog') or (user_id is not null and scope_key = user_id::text))
);
create index marquee_sync_state_success_run_idx on public.marquee_sync_state (last_success_run_id);

-- Explicit table-by-table privilege boundary. No schema-wide grant/revoke.
revoke all on table
  public.marquee_titles, public.marquee_shows, public.marquee_movies,
  public.marquee_seasons, public.marquee_episodes,
  public.marquee_watch_history, public.marquee_watch_history_sources,
  public.marquee_statuses, public.marquee_ratings, public.marquee_watchlist,
  public.marquee_source_mappings, public.marquee_franchise_overrides,
  public.marquee_mapping_review, public.marquee_sync_runs,
  public.marquee_ingest_raw, public.marquee_sync_state
from public, anon, authenticated;

alter table public.marquee_titles enable row level security;
alter table public.marquee_shows enable row level security;
alter table public.marquee_movies enable row level security;
alter table public.marquee_seasons enable row level security;
alter table public.marquee_episodes enable row level security;
alter table public.marquee_watch_history enable row level security;
alter table public.marquee_watch_history_sources enable row level security;
alter table public.marquee_statuses enable row level security;
alter table public.marquee_ratings enable row level security;
alter table public.marquee_watchlist enable row level security;
alter table public.marquee_source_mappings enable row level security;
alter table public.marquee_franchise_overrides enable row level security;
alter table public.marquee_mapping_review enable row level security;
alter table public.marquee_sync_runs enable row level security;
alter table public.marquee_ingest_raw enable row level security;
alter table public.marquee_sync_state enable row level security;

grant select on table public.marquee_titles, public.marquee_shows,
  public.marquee_movies, public.marquee_seasons, public.marquee_episodes
to authenticated;
grant select, insert, update, delete on table
  public.marquee_watch_history, public.marquee_statuses,
  public.marquee_ratings, public.marquee_watchlist to authenticated;

grant select, insert, update, delete on table
  public.marquee_titles, public.marquee_shows, public.marquee_movies,
  public.marquee_seasons, public.marquee_episodes,
  public.marquee_watch_history, public.marquee_watch_history_sources,
  public.marquee_statuses, public.marquee_ratings, public.marquee_watchlist,
  public.marquee_source_mappings, public.marquee_franchise_overrides,
  public.marquee_mapping_review,
  public.marquee_ingest_raw, public.marquee_sync_state
to service_role;
grant select, insert, update on table public.marquee_sync_runs to service_role;

create policy marquee_titles_read on public.marquee_titles for select to authenticated using (true);
create policy marquee_shows_read on public.marquee_shows for select to authenticated using (true);
create policy marquee_movies_read on public.marquee_movies for select to authenticated using (true);
create policy marquee_seasons_read on public.marquee_seasons for select to authenticated using (true);
create policy marquee_episodes_read on public.marquee_episodes for select to authenticated using (true);

create policy marquee_history_select on public.marquee_watch_history for select to authenticated
  using ((select auth.uid()) = user_id);
create policy marquee_history_insert on public.marquee_watch_history for insert to authenticated
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_history_update on public.marquee_watch_history for update to authenticated
  using ((select auth.uid()) = user_id and source = 'manual')
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_history_delete on public.marquee_watch_history for delete to authenticated
  using ((select auth.uid()) = user_id and source = 'manual');

create policy marquee_status_select on public.marquee_statuses for select to authenticated
  using ((select auth.uid()) = user_id);
create policy marquee_status_insert on public.marquee_statuses for insert to authenticated
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_status_update on public.marquee_statuses for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_status_delete on public.marquee_statuses for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy marquee_rating_select on public.marquee_ratings for select to authenticated
  using ((select auth.uid()) = user_id);
create policy marquee_rating_insert on public.marquee_ratings for insert to authenticated
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_rating_update on public.marquee_ratings for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_rating_delete on public.marquee_ratings for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy marquee_watchlist_select on public.marquee_watchlist for select to authenticated
  using ((select auth.uid()) = user_id);
create policy marquee_watchlist_insert on public.marquee_watchlist for insert to authenticated
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_watchlist_update on public.marquee_watchlist for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and source = 'manual');
create policy marquee_watchlist_delete on public.marquee_watchlist for delete to authenticated
  using ((select auth.uid()) = user_id);
