-- Explicit, reviewed weekly release schedules. These describe availability,
-- never a watch event, and do not create episodes or alter source evidence.
create table public.marquee_season_release_schedules (
  season_id uuid primary key references public.marquee_seasons(id),
  first_release_on date not null,
  interval_days integer not null check (interval_days > 0),
  planned_episodes integer not null check (planned_episodes > 0),
  source_url text not null,
  reviewed_at timestamptz not null default now()
);
alter table public.marquee_season_release_schedules enable row level security;
revoke all on public.marquee_season_release_schedules from public, anon, authenticated;
grant select on public.marquee_season_release_schedules to authenticated;
grant select, insert, update, delete on public.marquee_season_release_schedules to service_role;
create policy marquee_season_release_schedules_read
  on public.marquee_season_release_schedules for select to authenticated using (true);

insert into public.marquee_season_release_schedules
  (season_id, first_release_on, interval_days, planned_episodes, source_url)
select s.id, date '2026-08-05', 7, 10,
  'https://www.apple.com/tv-pr/news/2026/07/apple-tvs-emmy-award-winning-and-globally-beloved-hit-series-ted-lasso-returns-to-the-pitch-in-season-four-trailer/'
from public.marquee_seasons s
join public.marquee_titles t on t.id = s.show_title_id
where t.display_title = 'Ted Lasso' and s.season_number = 4;
