-- Read-only ongoing checks. Run after import; every result should have zero rows
-- except the explicit summary counts.

select user_id, logical_event_key, count(*) from public.marquee_watch_history
group by user_id, logical_event_key having count(*) > 1;

select user_id, source, source_entity_type, source_record_id, count(*)
from public.marquee_watch_history_sources
group by user_id, source, source_entity_type, source_record_id having count(*) > 1;

select source, source_entity_type, source_id, count(*) from public.marquee_source_mappings
group by source, source_entity_type, source_id having count(*) > 1;

select scope_key, source, source_entity_type, dedupe_key, count(*) from public.marquee_ingest_raw
group by scope_key, source, source_entity_type, dedupe_key having count(*) > 1;

select source, source_entity_type, source_id, count(*) from public.marquee_mapping_review
where status = 'open' group by source, source_entity_type, source_id having count(*) > 1;

select r.id, r.user_id, h.user_id as history_owner
from public.marquee_watch_history_sources r
join public.marquee_watch_history h on h.id = r.history_id
where r.user_id <> h.user_id;

-- Review these with the run's expected source count and adapter logs. Pending
-- or error raw rows from a supposedly successful run require investigation.
select r.source, r.scope_key, r.id as run_id, r.fetched_count,
       count(raw.id) filter (where raw.normalization_status in ('pending', 'error')) as incomplete_first_seen_raw
from public.marquee_sync_runs r
left join public.marquee_ingest_raw raw on raw.first_sync_run_id = r.id
where r.status = 'succeeded'
group by r.source, r.scope_key, r.id, r.fetched_count
having count(raw.id) filter (where raw.normalization_status in ('pending', 'error')) > 0;

select s.source, s.scope_key, s.last_success_run_id
from public.marquee_sync_state s
left join public.marquee_sync_runs r on r.id = s.last_success_run_id
where s.last_success_run_id is not null
  and (r.id is null or r.status <> 'succeeded' or r.source <> s.source or r.scope_key <> s.scope_key);

select source, scope_key, status, count(*) as runs, max(started_at) as latest_start
from public.marquee_sync_runs group by source, scope_key, status order by source, scope_key, status;

-- Phase 2 acceptance uses sanitized fixtures: import each twice, replay the
-- raw record, fix a mapping and replay again, inject failure before checkpoint
-- commit, and confirm canonical counts / watermark are unchanged on retry.
