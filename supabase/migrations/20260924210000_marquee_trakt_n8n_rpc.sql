-- Service-role-only Trakt snapshot importer. All six feeds are one transaction.
-- The scheduled n8n workflow fetches and validates complete pages before calling this RPC.
create or replace function public.marquee_trakt_mapping_target(
  p_source text, p_kind text, p_id text
) returns uuid language sql stable set search_path = '' as $$
  select coalesce(m.title_id, m.show_title_id, m.movie_title_id, m.season_id, m.episode_id)
  from public.marquee_source_mappings m
  where m.source=p_source and m.source_entity_type=p_kind and m.source_id=p_id
$$;

create or replace function public.marquee_trakt_add_mapping(
  p_source text, p_kind text, p_id text, p_target_kind text, p_target uuid
) returns void language plpgsql set search_path = '' as $$
declare old_target uuid;
begin
  if p_id is null or btrim(p_id)='' then
    raise exception using errcode='PT001', message='missing stable external ID';
  end if;
  select coalesce(title_id,show_title_id,movie_title_id,season_id,episode_id)
    into old_target from public.marquee_source_mappings
    where source=p_source and source_entity_type=p_kind and source_id=p_id;
  if found then
    if old_target is distinct from p_target then
      raise exception using errcode='PT001', message='conflicting stable external ID';
    end if;
    return;
  end if;
  if p_target_kind='show' then
    insert into public.marquee_source_mappings(source,source_entity_type,source_id,canonical_entity_type,show_title_id,match_method)
      values(p_source,p_kind,p_id,'show',p_target,'external_id');
  elsif p_target_kind='movie' then
    insert into public.marquee_source_mappings(source,source_entity_type,source_id,canonical_entity_type,movie_title_id,match_method)
      values(p_source,p_kind,p_id,'movie',p_target,'external_id');
  elsif p_target_kind='episode' then
    insert into public.marquee_source_mappings(source,source_entity_type,source_id,canonical_entity_type,episode_id,match_method)
      values(p_source,p_kind,p_id,'episode',p_target,'external_id');
  else
    raise exception 'unsupported Trakt mapping kind';
  end if;
end;
$$;

create or replace function public.marquee_trakt_resolve_catalog(
  p_kind text, p_media jsonb, p_approved jsonb
) returns uuid language plpgsql set search_path = '' as $$
declare
  v_ids jsonb:=p_media->'ids'; v_trakt text:=v_ids->>'trakt'; v_source text;
  v_other uuid; v_target uuid; v_old uuid; v_type text; v_anime boolean;
  v_title text:=p_media->>'title'; v_year int;
begin
  if p_kind not in ('show','movie') or jsonb_typeof(v_ids)<>'object' or nullif(btrim(v_trakt),'') is null then
    raise exception using errcode='PT001', message='missing media IDs';
  end if;
  select coalesce(title_id,show_title_id,movie_title_id),canonical_entity_type
    into v_target,v_type from public.marquee_source_mappings
    where source='trakt' and source_entity_type=p_kind and source_id=v_trakt;
  if found and v_type not in (p_kind,'title') then
    raise exception using errcode='PT001', message='Trakt mapping points to a different entity type';
  end if;
  foreach v_source in array array['tmdb','imdb'] loop
    if v_ids->>v_source is not null then
      select coalesce(title_id,show_title_id,movie_title_id) into v_other
        from public.marquee_source_mappings
        where source=v_source and source_entity_type=p_kind and source_id=v_ids->>v_source;
      if v_other is not null then
        if v_target is not null and v_other<>v_target then
          raise exception using errcode='PT001', message='external IDs point to different canonical records';
        end if;
        v_target:=v_other;
      end if;
    end if;
  end loop;
  if p_kind='show' and v_target is null and not (p_approved ? v_trakt) then
    raise exception using errcode='PT001', message='TV show not approved as non-anime';
  end if;
  if v_target is not null then
    select media_type,is_anime into v_type,v_anime from public.marquee_titles where id=v_target;
    if not found or v_type<>p_kind or (p_kind='show' and v_anime)
       or (p_kind='show' and not exists(select 1 from public.marquee_shows where title_id=v_target))
       or (p_kind='movie' and not exists(select 1 from public.marquee_movies where title_id=v_target)) then
      raise exception using errcode='PT001', message='existing catalog identity conflicts with Trakt media type or anime boundary';
    end if;
  else
    if nullif(btrim(v_title),'') is null then
      raise exception using errcode='PT001', message='missing display title';
    end if;
    if p_media->'year' is not null then
      if jsonb_typeof(p_media->'year')<>'number' or (p_media->>'year') !~ '^[0-9]{4}$' then
        raise exception using errcode='PT001', message='invalid release year';
      end if;
      v_year:=(p_media->>'year')::int;
      if v_year not between 1880 and 2200 then
        raise exception using errcode='PT001', message='invalid release year';
      end if;
    end if;
    insert into public.marquee_titles(media_type,display_title,release_year)
      values(p_kind,v_title,v_year) returning id into v_target;
    if p_kind='show' then
      insert into public.marquee_shows(title_id) values(v_target);
    else
      insert into public.marquee_movies(title_id) values(v_target);
    end if;
  end if;
  perform public.marquee_trakt_add_mapping('trakt',p_kind,v_trakt,p_kind,v_target);
  foreach v_source in array array['tmdb','imdb'] loop
    if v_ids->>v_source is not null then
      perform public.marquee_trakt_add_mapping(v_source,p_kind,v_ids->>v_source,p_kind,v_target);
    end if;
  end loop;
  return v_target;
end;
$$;

create or replace function public.marquee_trakt_resolve_episode(
  p_item jsonb, p_approved jsonb
) returns uuid language plpgsql set search_path = '' as $$
declare
  v_show uuid; v_season int; v_number int; v_season_id uuid;
  v_target uuid; v_existing uuid; v_trakt text:=p_item#>>'{episode,ids,trakt}';
begin
  v_show:=public.marquee_trakt_resolve_catalog('show',p_item->'show',p_approved);
  if jsonb_typeof(p_item#>'{episode,season}')<>'number' or
     (p_item#>>'{episode,season}') !~ '^[0-9]+$' or
     jsonb_typeof(p_item#>'{episode,number}')<>'number' or
     (p_item#>>'{episode,number}') !~ '^[0-9]+$' then
    raise exception using errcode='PT001', message='episode lacks valid season or episode number';
  end if;
  v_season:=(p_item#>>'{episode,season}')::int;
  v_number:=(p_item#>>'{episode,number}')::int;
  if v_number<=0 or nullif(btrim(v_trakt),'') is null then
    raise exception using errcode='PT001', message='episode lacks a positive number or stable ID';
  end if;
  select id into v_season_id from public.marquee_seasons
    where show_title_id=v_show and season_number=v_season;
  if v_season_id is null then
    insert into public.marquee_seasons(show_title_id,season_number)
      values(v_show,v_season) returning id into v_season_id;
  end if;
  select id into v_target from public.marquee_episodes
    where season_id=v_season_id and episode_number=v_number;
  v_existing:=public.marquee_trakt_mapping_target('trakt','episode',v_trakt);
  if v_existing is not null and v_target is not null and v_existing<>v_target then
    raise exception using errcode='PT001', message='episode ID conflicts with episode number';
  end if;
  if v_existing is not null and v_target is null then
    raise exception using errcode='PT001', message='mapped episode moved to a different number';
  end if;
  if v_target is not null and exists(
    select 1 from public.marquee_source_mappings where source='trakt' and source_entity_type='episode'
      and episode_id=v_target and source_id<>v_trakt
  ) then
    raise exception using errcode='PT001', message='another stable episode ID uses this number';
  end if;
  if v_target is null then
    insert into public.marquee_episodes(season_id,episode_number,display_title)
      values(v_season_id,v_number,p_item#>>'{episode,title}') returning id into v_target;
  end if;
  perform public.marquee_trakt_add_mapping('trakt','episode',v_trakt,'episode',v_target);
  return v_target;
end;
$$;

revoke all on function public.marquee_trakt_mapping_target(text,text,text) from public,anon,authenticated;
revoke all on function public.marquee_trakt_add_mapping(text,text,text,text,uuid) from public,anon,authenticated;
revoke all on function public.marquee_trakt_resolve_catalog(text,jsonb,jsonb) from public,anon,authenticated;
revoke all on function public.marquee_trakt_resolve_episode(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.marquee_trakt_mapping_target(text,text,text) to service_role;
grant execute on function public.marquee_trakt_add_mapping(text,text,text,text,uuid) to service_role;
grant execute on function public.marquee_trakt_resolve_catalog(text,jsonb,jsonb) to service_role;
grant execute on function public.marquee_trakt_resolve_episode(jsonb,jsonb) to service_role;

create or replace function public.marquee_trakt_apply_snapshot(
  p_user_id uuid, p_feeds jsonb, p_approved jsonb, p_execution_id text
) returns jsonb language plpgsql set search_path = '' as $$
declare
  v_scope text:=p_user_id::text;
  v_run uuid; v_feed text; v_item jsonb; v_media jsonb;
  v_kind text; v_media_id text; v_key text; v_at timestamptz;
  v_target uuid; v_history uuid; v_source text; v_locked boolean; v_previous timestamptz;
  v_seen jsonb:='{}'::jsonb; v_deleted int;
  v_watchlist uuid[]:=array[]::uuid[]; v_watchlist_reviewed boolean:=false;
  v_counts jsonb:='{}'::jsonb; v_fetched int:=0; v_inserted int:=0;
  v_updated int:=0; v_skipped int:=0; v_unmapped int:=0;
  v_result text; v_reason text; v_mapping uuid; v_title text;
begin
  if p_user_id is null or jsonb_typeof(p_feeds)<>'object' or
     jsonb_typeof(p_approved)<>'object' or nullif(btrim(p_execution_id),'') is null then
    raise exception 'invalid Trakt snapshot argument';
  end if;
  if not pg_catalog.pg_try_advisory_xact_lock(pg_catalog.hashtext('marquee.trakt'),pg_catalog.hashtext(v_scope)) then
    raise exception 'Trakt importer already running';
  end if;
  if (select count(*) from pg_catalog.jsonb_object_keys(p_feeds))<>6 then
    raise exception 'Trakt snapshot must contain exactly six feeds';
  end if;
  -- Validate every stable record ID and timestamp before any canonical writes.
  foreach v_feed in array array['history_movies','history_episodes','ratings_movies',
                              'ratings_shows','watchlist_movies','watchlist_shows'] loop
    if jsonb_typeof(p_feeds->v_feed)<>'array' then
      raise exception 'missing Trakt feed %',v_feed;
    end if;
    v_counts:=v_counts||pg_catalog.jsonb_build_object(v_feed,pg_catalog.jsonb_array_length(p_feeds->v_feed));
    for v_item in select value from pg_catalog.jsonb_array_elements(p_feeds->v_feed) loop
      v_kind:=case when v_feed='history_episodes' then 'episode'
                   when v_feed like '%movies' then 'movie' else 'show' end;
      v_media:=v_item->v_kind;
      v_media_id:=v_media#>>'{ids,trakt}';
      v_key:=case when v_feed like 'history_%' then v_item->>'id' else v_media_id end;
      if jsonb_typeof(v_item)<>'object' or jsonb_typeof(v_media)<>'object' or
         jsonb_typeof(v_media->'ids')<>'object' or
         nullif(btrim(v_media_id),'') is null or nullif(btrim(v_key),'') is null or
         (v_kind='episode' and nullif(btrim(v_item#>>'{show,ids,trakt}'),'') is null) then
        raise exception 'Trakt % missing stable identity',v_feed;
      end if;
      if v_feed like 'history_%' then v_title:=v_item->>'watched_at';
      elsif v_feed like 'ratings_%' then v_title:=v_item->>'rated_at';
      else v_title:=v_item->>'listed_at'; end if;
      if v_title is null or v_title !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' then
        raise exception 'Trakt % timestamp requires timezone',v_feed;
      end if;
      perform v_title::timestamptz;
      if v_feed like 'ratings_%' and
         (jsonb_typeof(v_item->'rating')<>'number' or
          (v_item->>'rating') !~ '^([1-9]|10)$') then
        raise exception 'Trakt rating outside 1..10';
      end if;
      if v_seen ? (v_feed||':'||v_key) then
        raise exception 'duplicate Trakt source record in %',v_feed;
      end if;
      v_seen:=v_seen||pg_catalog.jsonb_build_object(v_feed||':'||v_key,true);
    end loop;
  end loop;
  insert into public.marquee_sync_runs(source,user_id,scope_key,execution_id)
    values('trakt',p_user_id,v_scope,p_execution_id) returning id into v_run;
  foreach v_feed in array array['history_movies','history_episodes','ratings_movies',
                              'ratings_shows','watchlist_movies','watchlist_shows'] loop
    for v_item in select value from pg_catalog.jsonb_array_elements(p_feeds->v_feed) loop
      v_kind:=case when v_feed='history_episodes' then 'episode'
                   when v_feed like '%movies' then 'movie' else 'show' end;
      v_media:=v_item->v_kind;
      v_media_id:=v_media#>>'{ids,trakt}';
      v_key:=case when v_feed like 'history_%' then v_item->>'id' else v_media_id end;
      v_at:=case when v_feed like 'history_%' then (v_item->>'watched_at')::timestamptz
                 when v_feed like 'ratings_%' then (v_item->>'rated_at')::timestamptz
                 else (v_item->>'listed_at')::timestamptz end;
      v_fetched:=v_fetched+1;
      insert into public.marquee_ingest_raw
        (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,payload_hash,payload,first_sync_run_id)
        values('trakt',v_feed,v_media_id,p_user_id,v_scope,v_key,
          pg_catalog.encode(extensions.digest(pg_catalog.convert_to(v_item::text,'UTF8'),'sha256'),'hex'),v_item,v_run)
        on conflict(scope_key,source,source_entity_type,dedupe_key) do update
          set payload_hash=excluded.payload_hash,payload=excluded.payload,last_seen_at=now();
      begin
        v_target:=case when v_kind='episode'
          then public.marquee_trakt_resolve_episode(v_item,p_approved)
          else public.marquee_trakt_resolve_catalog(v_kind,v_media,p_approved) end;
        v_result:='skipped';
        if v_feed like 'history_%' then
          select history_id into v_history from public.marquee_watch_history_sources
            where user_id=p_user_id and source='trakt' and source_entity_type=v_kind
              and source_record_id=v_key;
          if v_history is not null then
            update public.marquee_watch_history
              set watched_at=v_at,source_updated_at=v_at,updated_at=now()
              where user_id=p_user_id and id=v_history and source='trakt'
                and watched_at is distinct from v_at;
            if found then v_result:='updated'; end if;
          else
            if v_kind='movie' then
              insert into public.marquee_watch_history
                (user_id,movie_title_id,logical_event_key,watched_at,source,source_record_id,source_updated_at)
                values(p_user_id,v_target,'trakt:movie:'||v_key,v_at,'trakt',v_key,v_at)
                on conflict(user_id,logical_event_key) do update
                  set source_updated_at=excluded.source_updated_at returning id into v_history;
            else
              insert into public.marquee_watch_history
                (user_id,episode_id,logical_event_key,watched_at,source,source_record_id,source_updated_at)
                values(p_user_id,v_target,'trakt:episode:'||v_key,v_at,'trakt',v_key,v_at)
                on conflict(user_id,logical_event_key) do update
                  set source_updated_at=excluded.source_updated_at returning id into v_history;
            end if;
            insert into public.marquee_watch_history_sources
              (user_id,history_id,source,source_entity_type,source_record_id,observed_at)
              values(p_user_id,v_history,'trakt',v_kind,v_key,v_at) on conflict do nothing;
            v_result:='inserted';
          end if;
        elsif v_feed like 'ratings_%' then
          select source,manual_locked,source_updated_at into v_source,v_locked,v_previous
            from public.marquee_ratings where user_id=p_user_id and title_id=v_target;
          if found and (v_locked or v_source='manual' or (v_previous is not null and v_previous>v_at)) then
            v_result:='skipped';
          else
            insert into public.marquee_ratings(user_id,title_id,score,source,source_record_id,source_updated_at)
              values(p_user_id,v_target,(v_item->>'rating')::int,'trakt',v_media_id,v_at)
              on conflict(user_id,title_id) where title_id is not null do update
              set score=excluded.score,source='trakt',source_record_id=excluded.source_record_id,
                  source_updated_at=excluded.source_updated_at,updated_at=now()
              where public.marquee_ratings.manual_locked=false and public.marquee_ratings.source<>'manual'
                and (public.marquee_ratings.source_updated_at is null or
                     public.marquee_ratings.source_updated_at<=excluded.source_updated_at);
            v_result:=case when v_source is null then 'inserted' else 'updated' end;
          end if;
        else
          select source,manual_locked into v_source,v_locked from public.marquee_watchlist
            where user_id=p_user_id and title_id=v_target;
          if found and (v_locked or v_source='manual') then
            v_result:='skipped';
          else
            insert into public.marquee_watchlist(user_id,title_id,source,source_record_id,source_updated_at,added_at)
              values(p_user_id,v_target,'trakt',v_media_id,v_at,v_at)
              on conflict(user_id,title_id) do update
              set source='trakt',source_record_id=excluded.source_record_id,
                  source_updated_at=excluded.source_updated_at,updated_at=now()
              where public.marquee_watchlist.manual_locked=false and public.marquee_watchlist.source<>'manual';
            v_result:=case when v_source is null then 'inserted' else 'updated' end;
          end if;
        end if;
      exception when sqlstate 'PT001' then
        get stacked diagnostics v_reason=message_text;
        v_result:='review';
      end;
      if v_result='review' then
        v_unmapped:=v_unmapped+1;
        if v_feed like 'watchlist_%' then v_watchlist_reviewed:=true; end if;
        insert into public.marquee_mapping_review(source,source_entity_type,source_id,source_title,reason)
          values('trakt',v_kind,v_media_id,v_media->>'title',v_reason)
          on conflict(source,source_entity_type,source_id) where status='open'
          do update set reason=excluded.reason,source_title=excluded.source_title;
      else
        if v_result='inserted' then v_inserted:=v_inserted+1;
        elsif v_result='updated' then v_updated:=v_updated+1;
        else v_skipped:=v_skipped+1; end if;
        select id into v_mapping from public.marquee_source_mappings
          where source='trakt' and source_entity_type=v_kind and source_id=v_media_id;
        update public.marquee_mapping_review set status='resolved',resolved_at=now(),
          resolved_mapping_id=v_mapping,resolution_notes='Resolved by stable source mapping'
          where source='trakt' and source_entity_type=v_kind and source_id=v_media_id and status='open';
        if v_feed like 'watchlist_%' then v_watchlist:=pg_catalog.array_append(v_watchlist,v_target); end if;
      end if;
      update public.marquee_ingest_raw set normalization_status=case when v_result='review' then 'review' else 'mapped' end,
        normalization_error=null where scope_key=v_scope and source='trakt'
          and source_entity_type=v_feed and dedupe_key=v_key;
    end loop;
  end loop;
  if not v_watchlist_reviewed then
    delete from public.marquee_watchlist where user_id=p_user_id and source='trakt'
      and manual_locked=false and not (title_id=any(v_watchlist));
    get diagnostics v_deleted = row_count;
    v_updated:=v_updated+v_deleted;
  end if;
  update public.marquee_sync_runs set status='succeeded',finished_at=now(),
    fetched_count=v_fetched,inserted_count=v_inserted,updated_count=v_updated,
    skipped_count=v_skipped,unmapped_count=v_unmapped
    where id=v_run and status='running';
  if not found then raise exception 'Trakt sync run did not finish'; end if;
  insert into public.marquee_sync_state
    (source,user_id,scope_key,watermark,last_attempt_at,last_success_at,last_success_run_id)
    values('trakt',p_user_id,v_scope,
      pg_catalog.jsonb_build_object('completed_at',now(),'feeds',v_counts),now(),now(),v_run)
    on conflict(source,scope_key) do update set watermark=excluded.watermark,
      last_attempt_at=now(),last_success_at=now(),last_success_run_id=excluded.last_success_run_id,
      last_error=null,consecutive_failures=0,updated_at=now();
  return pg_catalog.jsonb_build_object('fetched',v_fetched,'inserted',v_inserted,
    'updated',v_updated,'skipped',v_skipped,'unmapped',v_unmapped,'run_id',v_run);
end;
$$;

revoke all on function public.marquee_trakt_apply_snapshot(uuid,jsonb,jsonb,text) from public,anon,authenticated;
grant execute on function public.marquee_trakt_apply_snapshot(uuid,jsonb,jsonb,text) to service_role;
