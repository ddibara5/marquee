-- One canonical target per user in progress queries, across dated Trakt and
-- undated manual/Crunchyroll evidence. This view exposes no unverified date.
create view public.marquee_episode_completion_coverage
with (security_invoker = true) as
select user_id, episode_id,
       bool_or(dated) as has_dated_watch,
       bool_or(undated) as has_undated_completion
from (
  select user_id, episode_id, true as dated, false as undated
  from public.marquee_watch_history where episode_id is not null
  union all
  select user_id, episode_id, false as dated, true as undated
  from public.marquee_undated_completions where episode_id is not null
) evidence
group by user_id, episode_id;

create view public.marquee_movie_completion_coverage
with (security_invoker = true) as
select user_id, movie_title_id,
       bool_or(dated) as has_dated_watch,
       bool_or(undated) as has_undated_completion
from (
  select user_id, movie_title_id, true as dated, false as undated
  from public.marquee_watch_history where movie_title_id is not null
  union all
  select user_id, movie_title_id, false as dated, true as undated
  from public.marquee_undated_completions where movie_title_id is not null
) evidence
group by user_id, movie_title_id;

revoke all on public.marquee_episode_completion_coverage,
  public.marquee_movie_completion_coverage from public, anon, authenticated;
grant select on public.marquee_episode_completion_coverage,
  public.marquee_movie_completion_coverage to authenticated, service_role;
