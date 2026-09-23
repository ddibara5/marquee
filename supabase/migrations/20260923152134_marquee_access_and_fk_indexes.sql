-- Marquee-only follow-up to the initial ingestion foundation migration.
-- Explicit denials document service-only tables and quiet the RLS advisor.
-- No global grants, GameDeck objects, or default privileges are changed.

create policy marquee_franchise_overrides_service_only
  on public.marquee_franchise_overrides for all to anon, authenticated
  using (false) with check (false);
create policy marquee_ingest_raw_service_only
  on public.marquee_ingest_raw for all to anon, authenticated
  using (false) with check (false);
create policy marquee_mapping_review_service_only
  on public.marquee_mapping_review for all to anon, authenticated
  using (false) with check (false);
create policy marquee_source_mappings_service_only
  on public.marquee_source_mappings for all to anon, authenticated
  using (false) with check (false);
create policy marquee_sync_runs_service_only
  on public.marquee_sync_runs for all to anon, authenticated
  using (false) with check (false);
create policy marquee_sync_state_service_only
  on public.marquee_sync_state for all to anon, authenticated
  using (false) with check (false);
create policy marquee_watch_history_sources_service_only
  on public.marquee_watch_history_sources for all to anon, authenticated
  using (false) with check (false);

-- Reverse FK lookup indexes for auth-user removal and catalog corrections.
create index marquee_ingest_raw_user_idx on public.marquee_ingest_raw (user_id);
create index marquee_ratings_title_fk_idx on public.marquee_ratings (title_id);
create index marquee_ratings_season_fk_idx on public.marquee_ratings (season_id);
create index marquee_statuses_title_fk_idx on public.marquee_statuses (title_id);
create index marquee_statuses_season_fk_idx on public.marquee_statuses (season_id);
create index marquee_sync_runs_user_idx on public.marquee_sync_runs (user_id);
create index marquee_sync_state_user_idx on public.marquee_sync_state (user_id);
create index marquee_history_episode_fk_idx on public.marquee_watch_history (episode_id);
create index marquee_history_movie_fk_idx on public.marquee_watch_history (movie_title_id);
create index marquee_history_sources_owner_fk_idx on public.marquee_watch_history_sources (user_id, history_id);

-- The composite FKs on marquee_shows and marquee_movies start with title_id,
-- already covered by each table's primary-key index. Duplicate composite
-- indexes would add maintenance cost for no useful selectivity.
