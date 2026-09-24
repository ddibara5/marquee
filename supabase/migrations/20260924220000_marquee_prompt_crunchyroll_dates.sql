-- Source-reported dates only for a newly observed live incremental event.
-- Historical backfill remains undated; original raw and undated evidence remain intact.
create table public.marquee_watch_date_decisions (
  raw_id uuid primary key references public.marquee_ingest_raw(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  history_id uuid not null,
  policy text not null check (policy = 'crunchyroll_prompt_incremental_48h_v1'),
  source_played_at timestamptz not null,
  first_observed_at timestamptz not null,
  decided_at timestamptz not null default now(),
  foreign key (user_id,history_id) references public.marquee_watch_history(user_id,id) on delete cascade
);
create index marquee_watch_date_decisions_history_idx on public.marquee_watch_date_decisions(history_id);
alter table public.marquee_watch_date_decisions enable row level security;
revoke all on public.marquee_watch_date_decisions from anon, authenticated;
grant select, insert on public.marquee_watch_date_decisions to service_role;

create function public.marquee_record_prompt_crunchyroll_watch(p_raw_id uuid, p_episode_id uuid)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare
  r record;
  played timestamptz;
  history_id uuid;
  identifier text;
begin
  select raw.id,raw.user_id,raw.dedupe_key,raw.payload,raw.fetched_at,
         run.execution_id, ep.aired_at
    into r
    from public.marquee_ingest_raw raw
    join public.marquee_sync_runs run on run.id=raw.first_sync_run_id
    join public.marquee_episodes ep on ep.id=p_episode_id
    where raw.id=p_raw_id and raw.source='crunchyroll'
      and raw.source_entity_type='history_event';
  if not found or coalesce(r.execution_id,'') !~ '^n8n:[0-9]+$'
     or r.payload->>'fully_watched' is distinct from 'true'
     or r.payload->>'parent_id' in ('GRMG8ZQZR','G6DQDD3WR')
     or r.payload #>> '{panel,episode_metadata,series_id}' in ('GRMG8ZQZR','G6DQDD3WR')
     or r.payload #>> '{panel,episode_metadata,series_id}'
          is distinct from r.payload->>'parent_id' then
    return false;
  end if;
  identifier := r.payload #>> '{panel,episode_metadata,identifier}';
  if not exists (select 1 from public.marquee_source_mappings m
      where m.source='crunchyroll' and m.source_entity_type='episode'
        and m.source_id=identifier and m.episode_id=p_episode_id and m.manual_locked)
     or not exists (select 1 from public.marquee_undated_completion_evidence evidence
      join public.marquee_undated_completions completion on completion.id=evidence.completion_id
      where evidence.raw_id=p_raw_id and evidence.source='crunchyroll'
        and completion.user_id=r.user_id and completion.episode_id=p_episode_id) then
    return false;
  end if;
  if r.payload->>'date_played' !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$' then
    return false;
  end if;
  begin
    played := (r.payload->>'date_played')::timestamptz;
  exception when datetime_field_overflow or invalid_datetime_format then
    return false;
  end;
  if played < '2026-09-24 00:00:00+00'::timestamptz
     or played > r.fetched_at + interval '5 minutes'
     or r.fetched_at > played + interval '48 hours'
     or (r.aired_at is not null and r.aired_at > played)
     or exists (select 1 from public.marquee_ingest_raw other
       where other.source='crunchyroll' and other.source_entity_type='history_event'
         and other.user_id=r.user_id and other.id<>p_raw_id
         and other.payload->>'date_played'=r.payload->>'date_played') then
    return false;
  end if;
  -- A re-run never changes a decision or invents another date. A source event
  -- always has its own identity; canonical coverage still counts the episode once.
  if exists (select 1 from public.marquee_watch_date_decisions where raw_id=p_raw_id) then
    return false;
  end if;
  insert into public.marquee_watch_history
    (user_id,episode_id,logical_event_key,watched_at,source,source_record_id)
  values (r.user_id,p_episode_id,'crunchyroll:history_event:'||r.dedupe_key,
          played,'crunchyroll',r.dedupe_key)
  on conflict (user_id,logical_event_key) do nothing
  returning id into history_id;
  if history_id is null then return false; end if;
  insert into public.marquee_watch_history_sources
    (user_id,history_id,source,source_entity_type,source_record_id,observed_at)
  values (r.user_id,history_id,'crunchyroll','history_event',r.dedupe_key,r.fetched_at);
  insert into public.marquee_watch_date_decisions
    (raw_id,user_id,history_id,policy,source_played_at,first_observed_at)
  values (p_raw_id,r.user_id,history_id,'crunchyroll_prompt_incremental_48h_v1',played,r.fetched_at);
  return true;
end;
$$;
revoke all on function public.marquee_record_prompt_crunchyroll_watch(uuid,uuid) from public, anon, authenticated;
grant execute on function public.marquee_record_prompt_crunchyroll_watch(uuid,uuid) to service_role;

-- The published n8n workflow calls the same RPC. Patch only its mapped branch;
-- fail migration if the reviewed version is no longer the one expected.
do $migration$
declare
  body text;
  before_text text := $old$      linked_count := linked_count + 1;
    end if;$old$;
  after_text text := $new$      linked_count := linked_count + 1;
      if target_episode is not null then
        perform public.marquee_record_prompt_crunchyroll_watch(raw_id,target_episode);
      end if;
    end if;$new$;
begin
  select pg_get_functiondef('public.marquee_ingest_crunchyroll_window(text,jsonb,text)'::regprocedure) into body;
  if position(before_text in body)=0 then
    raise exception 'Unexpected Marquee importer function version';
  end if;
  execute replace(body,before_text,after_text);
end;
$migration$;

-- These three events were first captured by the reviewed n8n run while
-- their episode mappings were still pending. Backfill only these IDs.
do $backfill$
declare
  entry record;
begin
  for entry in
    select raw.id,m.episode_id from public.marquee_ingest_raw raw
    join public.marquee_source_mappings m
      on m.source='crunchyroll' and m.source_entity_type='episode'
      and m.source_id=raw.payload #>> '{panel,episode_metadata,identifier}'
      and m.manual_locked
    where raw.source='crunchyroll' and raw.source_entity_type='history_event'
      and raw.dedupe_key in ('G2XU0G84J','G8WUN18E9','GEVUZDM5Q')
  loop
    if not public.marquee_record_prompt_crunchyroll_watch(entry.id,entry.episode_id) then
      raise exception 'Reviewed prompt event could not be dated';
    end if;
  end loop;
  if (select count(*) from public.marquee_watch_date_decisions
      where policy='crunchyroll_prompt_incremental_48h_v1')<>3 then
    raise exception 'Expected exactly three reviewed source date decisions';
  end if;
end;
$backfill$;
