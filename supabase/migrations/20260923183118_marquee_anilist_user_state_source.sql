-- Forward-only change scoped to Marquee user-state source checks.
-- Keep historical MAL values because removing them is not required for this adapter.
alter table public.marquee_statuses
  drop constraint marquee_statuses_source_check,
  add constraint marquee_statuses_source_check
    check (source in ('manual', 'trakt', 'crunchyroll', 'mal', 'anilist'));

alter table public.marquee_ratings
  drop constraint marquee_ratings_source_check,
  add constraint marquee_ratings_source_check
    check (source in ('manual', 'trakt', 'mal', 'anilist'));
