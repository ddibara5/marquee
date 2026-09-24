-- A source event whose stable identity changed cannot safely overwrite staged
-- evidence. Hold that event for review and continue the verified window.
do $migration$
declare
  body text;
  before_text text := $old$        raise exception 'A previously staged event changed identity';$old$;
  after_text text := $new$        insert into public.marquee_mapping_review
          (source,source_entity_type,source_id,reason)
        values ('crunchyroll','history_event',source_event_id,
          'A previously staged event changed identity; original evidence retained')
        on conflict (source,source_entity_type,source_id) where status='open' do nothing;
        held_count := held_count + 1;
        continue;$new$;
begin
  select pg_get_functiondef('public.marquee_ingest_crunchyroll_window(text,jsonb,text)'::regprocedure)
    into body;
  if position(before_text in body) = 0 then
    raise exception 'Unexpected Marquee importer function version';
  end if;
  execute replace(body,before_text,after_text);
end;
$migration$;
