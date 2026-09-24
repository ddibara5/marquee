-- Keep rejection reasons reviewable while suppressing event data and identifiers.
-- Start with the reviewed function and replace only its exception handler.
do $migration$
declare
  body text;
begin
  select pg_get_functiondef('public.marquee_ingest_crunchyroll_window(text,jsonb,text)'::regprocedure)
    into body;
  if body not like '%Marquee Crunchyroll window rejected (SQLSTATE %' then
    raise exception 'Unexpected Marquee importer function version';
  end if;
  body := replace(body,
    'raise exception ''Marquee Crunchyroll window rejected (SQLSTATE %)'',SQLSTATE;',
    $replacement$if SQLERRM = any(array[
      'Invalid incremental input',
      'Recent history window is outside the reviewed 40 to 400 event bounds',
      'Invalid execution identifier',
      'Expected one reviewed Crunchyroll profile',
      'Reviewed Crunchyroll checkpoint is unavailable',
      'Crunchyroll account differs from the reviewed profile',
      'GameDeck regression baseline changed',
      'Reviewed season-total catalog changed',
      'Recent history includes duplicate IDs or changed record shape',
      'Recent history window missed its reviewed overlap boundary',
      'Source series and parent are both unavailable',
      'A previously staged event changed identity',
      'Source episode identifier changed series',
      'Reviewed mapping does not resolve to exactly one target',
      'Completion target was not persisted',
      'Existing raw evidence points to a different completion'
    ]) then
      raise exception 'Marquee Crunchyroll window rejected: %',SQLERRM;
    end if;
    raise exception 'Marquee Crunchyroll window rejected (SQLSTATE %)',SQLSTATE;$replacement$);
  execute body;
end;
$migration$;
