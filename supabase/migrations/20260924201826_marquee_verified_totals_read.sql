-- Reviewed season totals are catalog metadata, like marquee_seasons. Keep
-- writes reserved to service_role; anonymous callers have no table grant.
grant select on table public.marquee_verified_season_totals to authenticated;
create policy marquee_verified_season_totals_read
  on public.marquee_verified_season_totals for select to authenticated
  using (true);
