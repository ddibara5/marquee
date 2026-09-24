-- Qualify PL/pgSQL variables that share names with evidence columns.
create or replace function public.marquee_ingest_crunchyroll_window(
  p_account_id text, p_events jsonb, p_execution_id text default null
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
<<ingest_window>>
declare
  owner_id uuid;
  scope_id text;
  old_watermark jsonb;
  expected_digest text;
  event_count integer;
  existing_tail integer;
  new_count integer := 0;
  changed_count integer := 0;
  linked_count integer := 0;
  held_count integer := 0;
  run_id uuid;
  entry record;
  item jsonb;
  source_event_id text;
  source_identifier text;
  source_series text;
  source_parent text;
  raw_id uuid;
  old_raw jsonb;
  target_episode uuid;
  target_movie uuid;
  completion_id uuid;
  target_season uuid;
  classification text;
begin
  if p_account_id is null or length(p_account_id) not between 10 and 128
     or p_account_id ~ '[^a-zA-Z0-9-]' or jsonb_typeof(p_events) is distinct from 'array' then
    raise exception 'Invalid incremental input';
  end if;
  event_count := jsonb_array_length(p_events);
  if event_count < 40 or event_count > 400 then
    raise exception 'Recent history window is outside the reviewed 40 to 400 event bounds';
  end if;
  if p_execution_id is not null and length(p_execution_id) > 120 then
    raise exception 'Invalid execution identifier';
  end if;

  if (select count(*) from public.marquee_sync_state where source='crunchyroll') <> 1 then
    raise exception 'Expected one reviewed Crunchyroll profile';
  end if;
  select user_id, scope_key, watermark into owner_id, scope_id, old_watermark
  from public.marquee_sync_state where source='crunchyroll' for update;
  if not found or owner_id is null or old_watermark->>'complete_event_count' is null then
    raise exception 'Reviewed Crunchyroll checkpoint is unavailable';
  end if;
  expected_digest := encode(extensions.digest(convert_to(p_account_id,'UTF8'),'sha256'),'hex');
  if old_watermark->>'account_digest' is distinct from expected_digest then
    raise exception 'Crunchyroll account differs from the reviewed profile';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtext('marquee:crunchyroll:' || scope_id));
  if (select count(*) from public.game_ranks) <> 53 or
     (select count(*) from public.rank_comparisons) <> 154 then
    raise exception 'GameDeck regression baseline changed';
  end if;
  if (select count(*) from public.marquee_verified_season_totals) <> 80 then
    raise exception 'Reviewed season-total catalog changed';
  end if;
  if exists (
    select 1 from jsonb_array_elements(p_events) e
    where jsonb_typeof(e.value) is distinct from 'object'
       or jsonb_typeof(e.value->'id') is distinct from 'string'
       or btrim(e.value->>'id') = ''
       or jsonb_typeof(e.value->'date_played') is distinct from 'string'
       or (e.value->>'date_played') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
       or jsonb_typeof(e.value->'fully_watched') is distinct from 'boolean'
  ) or (select count(distinct e.value->>'id') from jsonb_array_elements(p_events) e) <> event_count then
    raise exception 'Recent history includes duplicate IDs or changed record shape';
  end if;
  -- At least 40 pre-staged records at the old end of the ordered sample prove
  -- that the bounded window reached known history. Otherwise pause for review.
  select count(*) into existing_tail from
    jsonb_array_elements(p_events) with ordinality e(value,position)
    join public.marquee_ingest_raw r on r.source='crunchyroll'
      and r.source_entity_type='history_event' and r.scope_key=scope_id
      and r.dedupe_key=e.value->>'id'
    where e.position > event_count - 40;
  if existing_tail <> 40 then
    raise exception 'Recent history window missed its reviewed overlap boundary';
  end if;

  insert into public.marquee_sync_runs (source,user_id,scope_key,execution_id)
  values ('crunchyroll',owner_id,scope_id,p_execution_id) returning id into run_id;

  for entry in select value,position
     from jsonb_array_elements(p_events) with ordinality e(value,position)
     order by position loop
    item := entry.value;
    source_event_id := item->>'id';
    source_identifier := item #>> '{panel,episode_metadata,identifier}';
    source_series := item #>> '{panel,episode_metadata,series_id}';
    source_parent := item->>'parent_id';
    if source_series is null and source_parent is null then
      raise exception 'Source series and parent are both unavailable';
    end if;
    select id,payload into raw_id,old_raw from public.marquee_ingest_raw
      where source='crunchyroll' and source_entity_type='history_event'
        and scope_key=scope_id and dedupe_key=source_event_id;
    if found then
      if old_raw->>'date_played' is distinct from item->>'date_played'
         or old_raw #>> '{panel,id}' is distinct from item #>> '{panel,id}'
         or old_raw #>> '{panel,episode_metadata,identifier}'
            is distinct from source_identifier then
        raise exception 'A previously staged event changed identity';
      end if;
      if old_raw is distinct from item then changed_count := changed_count + 1; end if;
    else
      new_count := new_count + 1;
    end if;
    classification := 'review';
    target_episode := null;
    target_movie := null;
    if source_series in ('GRMG8ZQZR','G6DQDD3WR')
        or source_parent in ('GRMG8ZQZR','G6DQDD3WR') then
      classification := 'ignored';
    elsif source_identifier is not null then
      if exists (
        select 1 from public.marquee_ingest_raw previous
        where previous.source='crunchyroll'
          and previous.source_entity_type='history_event'
          and previous.scope_key=scope_id
          and previous.payload #>> '{panel,episode_metadata,identifier}'=source_identifier
          and previous.payload #>> '{panel,episode_metadata,series_id}'
            is distinct from source_series
      ) then
        raise exception 'Source episode identifier changed series';
      end if;
      select m.episode_id,m.movie_title_id into target_episode,target_movie
      from public.marquee_source_mappings m
      where m.source='crunchyroll' and m.source_entity_type='episode'
        and m.source_id=source_identifier and m.manual_locked=true;
      if found then classification := 'mapped'; end if;
    end if;

    insert into public.marquee_ingest_raw
      (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,
       payload_hash,payload,first_sync_run_id,normalization_status)
    values ('crunchyroll','history_event',source_event_id,owner_id,scope_id,
      source_event_id,encode(extensions.digest(convert_to(item::text,'UTF8'),'sha256'),'hex'),
      item,run_id,classification)
    on conflict (scope_key,source,source_entity_type,dedupe_key)
    do update set payload=excluded.payload,
      payload_hash=case when public.marquee_ingest_raw.payload is distinct from excluded.payload
                   then excluded.payload_hash else public.marquee_ingest_raw.payload_hash end,
      last_seen_at=now(),normalization_status=excluded.normalization_status
    returning id into raw_id;
    if classification='review' then
      held_count := held_count + 1;
      insert into public.marquee_mapping_review
        (source,source_entity_type,source_id,reason)
      values ('crunchyroll',
        case when source_identifier is null then 'history_event' else 'episode' end,
        coalesce(source_identifier,source_event_id),
        'Incremental event needs reviewed canonical episode identity')
      on conflict (source,source_entity_type,source_id) where status='open' do nothing;
    elsif classification='mapped' and item->>'fully_watched'='true' then
      if pg_catalog.num_nonnulls(target_episode,target_movie) <> 1 then
        raise exception 'Reviewed mapping does not resolve to exactly one target';
      end if;
      insert into public.marquee_undated_completions(user_id,episode_id,movie_title_id)
      values (owner_id,target_episode,target_movie) on conflict do nothing;
      select id into completion_id from public.marquee_undated_completions
      where user_id=owner_id
        and ((target_episode is not null and episode_id=target_episode)
         or (target_movie is not null and movie_title_id=target_movie));
      if completion_id is null then raise exception 'Completion target was not persisted'; end if;
      if exists (
        select 1 from public.marquee_undated_completion_evidence previous
        where previous.raw_id=ingest_window.raw_id and previous.source='crunchyroll'
          and previous.completion_id<>ingest_window.completion_id
      ) then
        raise exception 'Existing raw evidence points to a different completion';
      end if;
      insert into public.marquee_undated_completion_evidence
        (user_id,completion_id,raw_id,source,source_episode_identifier)
      values (owner_id,completion_id,raw_id,'crunchyroll',source_identifier)
      on conflict do nothing;
      linked_count := linked_count + 1;
    end if;
  end loop;

  -- Only media with reviewed published totals can acquire completed status.
  insert into public.marquee_statuses(user_id,season_id,status,source)
  select owner_id,v.season_id,'completed','crunchyroll'
  from public.marquee_verified_season_totals v
  where (select count(*) from public.marquee_episodes ep
         join public.marquee_episode_completion_coverage c
           on c.episode_id=ep.id and c.user_id=owner_id
         where ep.season_id=v.season_id)=v.episode_total
    and not exists(select 1 from public.marquee_statuses s
       where s.user_id=owner_id and s.season_id=v.season_id)
  on conflict do nothing;
  update public.marquee_statuses s set status='completed',source='crunchyroll',
    source_record_id=null,updated_at=now()
  from public.marquee_verified_season_totals v
  where s.user_id=owner_id and s.season_id=v.season_id
    and s.status<>'completed' and not s.manual_locked
    and (select count(*) from public.marquee_episodes ep
         join public.marquee_episode_completion_coverage c
           on c.episode_id=ep.id and c.user_id=owner_id
         where ep.season_id=v.season_id)=v.episode_total;

  update public.marquee_sync_runs set status='succeeded',finished_at=now(),
    fetched_count=event_count,inserted_count=new_count,updated_count=changed_count,
    skipped_count=event_count-new_count-changed_count,unmapped_count=held_count
    where id=run_id and status='running';
  update public.marquee_sync_state set
    watermark=old_watermark || jsonb_build_object(
      'complete_event_count',(old_watermark->>'complete_event_count')::integer+new_count,
      'recent_window_events',event_count),
    last_attempt_at=now(),last_success_at=now(),last_success_run_id=run_id,
    last_error=null,consecutive_failures=0,updated_at=now()
    where source='crunchyroll' and scope_key=scope_id;
  return jsonb_build_object('fetched',event_count,'new',new_count,
    'changed',changed_count,'held',held_count,'linked_evidence',linked_count);
exception when others then
  -- No event bodies, identifiers, cookies or request details reach n8n logs.
  raise exception 'Marquee Crunchyroll window rejected (SQLSTATE %)',SQLSTATE;
end;
$$;
