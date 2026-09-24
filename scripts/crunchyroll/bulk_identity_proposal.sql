-- Read-only owner-confirmed Crunchyroll identity proposal, 2026-09-24.
-- Run only against the staged Marquee snapshot, with service-role read access.
-- It returns one row per stable source identifier. No mapping or watch is written.
-- Source episode numbers are absolute for AoT/MHA and local for WT/HxH;
-- local_episode_number translates them into the AniList media entry.
-- There must be exactly one staged Crunchyroll scope; otherwise returns no rows.
with media_spec(label, series_id, source_season, first_number, last_number, anilist_media_id) as (
  values
  ('My Hero Academia S1', 'G6NQ5DWZ6', 'S00003205', 1, 13, 21459),
  ('My Hero Academia S2', 'G6NQ5DWZ6', 'S00003207', 14, 38, 21856),
  ('My Hero Academia S3', 'G6NQ5DWZ6', 'S00003757', 39, 63, 100166),
  ('My Hero Academia S4', 'G6NQ5DWZ6', 'S00089871', 64, 88, 104276),
  ('My Hero Academia S5', 'G6NQ5DWZ6', 'S00113970', 89, 113, 117193),
  ('My Hero Academia S6', 'G6NQ5DWZ6', 'S00256606', 114, 138, 139630),
  ('My Hero Academia S7', 'G6NQ5DWZ6', 'S00335713', 139, 159, 163139),
  ('My Hero Academia Final', 'G6NQ5DWZ6', 'S00355339', 160, 170, 182896),
  ('Attack on Titan S1', 'GR751KNZY', 'S1', 1, 25, 16498),
  ('Attack on Titan S2', 'GR751KNZY', 'S2', 26, 37, 20958),
  ('Attack on Titan S3 part 1', 'GR751KNZY', 'S3', 38, 49, 99147),
  ('Attack on Titan S3 part 2', 'GR751KNZY', 'S3', 50, 59, 104578),
  ('Attack on Titan Final part 1', 'GR751KNZY', 'S4', 60, 75, 110277),
  ('Attack on Titan Final part 2', 'GR751KNZY', 'S4', 76, 87, 131681),
  ('World Trigger S1', 'GR757DMKY', 'S00170952', 1, 73, 20729),
  ('World Trigger S2', 'GR757DMKY', 'S00170965', 1, 12, 114087),
  ('World Trigger S3', 'GR757DMKY', 'S00310086', 1, 14, 127400),
  ('Hunter x Hunter (2011)', 'GY3VKX1MR', 'S1', 1, 148, 11061),
  ('Gachiakuta S1', 'GP5HJ84P7', 'S00352501', 1, 24, 178025)
), exact_spec(label, source_identifier, anilist_media_id, target_kind, scope) as (
  values
  ('Attack on Titan Final Chapters SP1', 'GR751KNZY|S4|E88', 146984, 'episode', 'main'),
  ('Attack on Titan Final Chapters SP2', 'GR751KNZY|S4|E91', 162314, 'episode', 'main'),
  ('Link Click 5.5', 'GP5HJ8E81|S00113950|E6', null::integer, 'special_episode', 'selected_special'),
  ('Kaiju No. 8: Hoshina''s Day Off', 'GG5H5XQ7D|S00352541|E1', 179999, 'special_episode', 'selected_special'),
  ('Black Butler: Book of the Atlantic', 'GYQ43P3E6|M|E0', 21425, 'movie', 'selected_special')
), one_scope as (
  select min(scope_key) scope_key from public.marquee_ingest_raw
  where source = 'crunchyroll' and source_entity_type = 'history_event'
  having count(distinct scope_key) = 1 and count(*) = 7933
), observations as (
  select r.payload #>> '{panel,episode_metadata,identifier}' source_identifier,
         r.payload #>> '{panel,episode_metadata,series_id}' series_id,
         r.payload #>> '{panel,episode_metadata,episode_number}' source_number,
         (r.payload ->> 'fully_watched')::boolean complete,
         r.payload #>> '{panel,id}' panel_id
  from public.marquee_ingest_raw r cross join one_scope s
  where r.source = 'crunchyroll' and r.source_entity_type = 'history_event'
    and r.scope_key = s.scope_key
    and r.payload #>> '{panel,episode_metadata,identifier}' is not null
), episode_groups as (
  select source_identifier,
         min(series_id) series_id,
         split_part(source_identifier, '|', 2) source_season,
         min(case when source_number ~ '^[1-9][0-9]*$' then source_number::int end) source_number,
         count(distinct series_id) series_variants,
         count(distinct coalesce(source_number, '<no-number>')) number_variants,
         bool_or(complete) complete,
         count(*) observations,
         count(distinct panel_id) observed_versions
  from observations
  group by source_identifier
), proposed as (
  select g.*,
         coalesce(e.scope, case when m.label is not null and g.series_id = 'GP5HJ84P7'
           then 'confirmed_other' when m.label is not null then 'main'
           when g.series_id in ('G6NQ5DWZ6','GR751KNZY','GR757DMKY','GY3VKX1MR')
           then 'held_bulk_extra' end) scope,
         coalesce(e.label,m.label) target_label,
         coalesce(e.anilist_media_id,m.anilist_media_id) anilist_media_id,
         coalesce(e.target_kind,'episode') target_kind,
         case when e.source_identifier is null then g.source_number - m.first_number + 1 end local_episode_number,
         count(m.label) over (partition by g.source_identifier) range_matches
  from episode_groups g
  left join media_spec m on g.series_id = m.series_id and g.source_season = m.source_season
    and g.source_number between m.first_number and m.last_number
  left join exact_spec e on e.source_identifier = g.source_identifier
  where g.series_id in ('G6NQ5DWZ6','GR751KNZY','GR757DMKY','GY3VKX1MR','GP5HJ84P7')
     or e.source_identifier is not null
)
select source_identifier, series_id, source_season, source_number, scope,
       target_label, anilist_media_id, target_kind, local_episode_number,
       complete, observations, observed_versions,
       (series_variants = 1 and number_variants = 1 and range_matches <= 1) identity_consistent
from proposed
order by scope, target_label, local_episode_number nulls last, source_identifier;
