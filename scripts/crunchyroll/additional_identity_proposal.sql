-- Read-only identity proposal for all other non-excluded source shows, 2026-09-24.
-- Exact source series + season + integer episode ranges map to AniList catalog
-- media and local episode numbers. The remaining identifiers are explicitly held.
-- The three owner-selected specials/film are in bulk_identity_proposal.sql.
-- No episode, watch, status, mapping, or date is written by this query.
-- The source snapshot guard prevents silently running against a changed import.
with media_spec(label, series_id, source_season, first_number, last_number, anilist_media_id) as (
  values
  ('Blue Exorcist', 'G649PJ0JY', 'S00095472', 1, 25, 9919),
  ('Blue Exorcist: Kyoto Saga', 'G649PJ0JY', 'S00095473', 1, 12, 21861),
  ('Blue Exorcist: Shimane Illuminati Saga', 'G649PJ0JY', 'S00327937', 1, 12, 158931),
  ('Blue Exorcist: Beyond the Snow Saga', 'G649PJ0JY', 'S00346726', 1, 12, 176311),
  ('Blue Exorcist: The Blue Night Saga', 'G649PJ0JY', 'S00346727', 1, 12, 185880),
  ('Code Geass', 'GY2P9ED0Y', 'S00002836', 1, 25, 1575),
  ('Code Geass R2', 'GY2P9ED0Y', 'S00002837', 1, 25, 2904),
  ('Demon Slayer S1', 'GY5P48XEY', 'S00058845', 1, 26, 101922),
  ('Demon Slayer Mugen Train TV', 'GY5P48XEY', 'S00118708', 1, 7, 129874),
  ('Demon Slayer Entertainment District', 'GY5P48XEY', 'S00117519', 1, 11, 142329),
  ('Demon Slayer Swordsmith Village', 'GY5P48XEY', 'S00264119', 1, 11, 145139),
  ('Demon Slayer Hashira Training', 'GY5P48XEY', 'S00336261', 1, 8, 166240),
  ('Dr. STONE S1', 'GYEXQKJG6', 'S00088720', 1, 24, 105333),
  ('Dr. STONE Stone Wars', 'GYEXQKJG6', 'S00107082', 1, 11, 113936),
  ('Dr. STONE New World part 1', 'GYEXQKJG6', 'S00253419', 1, 11, 131518),
  ('Dr. STONE New World part 2', 'GYEXQKJG6', 'S00253419', 12, 22, 162670),
  ('Dr. STONE Science Future part 1', 'GYEXQKJG6', 'S00346868', 1, 12, 172019),
  ('Dr. STONE Science Future part 2', 'GYEXQKJG6', 'S00346868', 13, 24, 189117),
  ('Dr. STONE Ryusui special', 'GYEXQKJG6', 'S00374284', 1, 1, 142876),
  ('Fire Force S1', 'GYQWNXPZY', 'S00059010', 1, 24, 105310),
  ('Fruits Basket (2019) S1', 'G6ZJMGEXY', 'S00058876', 1, 25, 105334),
  ('Fullmetal Alchemist: Brotherhood', 'GRGGPG93R', 'S00002992', 1, 64, 5114),
  ('Jujutsu Kaisen S1', 'GRDV0019R', 'S00170749', 1, 24, 113415),
  ('Jujutsu Kaisen S2', 'GRDV0019R', 'S00267967', 25, 47, 145064),
  ('Jujutsu Kaisen Culling Game part 1', 'GRDV0019R', 'S00365546', 48, 59, 172463),
  ('Michiko & Hatchin', 'G6Q4Z8PQR', 'S00003183', 1, 22, 4087),
  ('Solo Leveling S1', 'GDKHZEJ0K', 'S00320668', 1, 12, 151807),
  ('Solo Leveling S2', 'GDKHZEJ0K', 'S00346859', 13, 25, 176496),
  ('Spy x Family cour 1', 'G4PH0WXVJ', 'S00166337', 1, 12, 140960),
  ('Spy x Family cour 2', 'G4PH0WXVJ', 'S00166337', 13, 25, 142838),
  ('Spy x Family Season 2', 'G4PH0WXVJ', 'S00319928', 26, 37, 158927),
  ('Sword Art Online S1', 'GR49G9VP6', 'S00058615', 1, 25, 11757),
  ('Sword Art Online II', 'GR49G9VP6', 'S00058641', 1, 24, 20594),
  ('Sword Art Online Alicization', 'GR49G9VP6', 'S00058496', 1, 24, 100182),
  ('Sword Art Online Underworld part 1', 'GR49G9VP6', 'S00058666', 1, 12, 108759),
  ('Sword Art Online Underworld part 2', 'GR49G9VP6', 'S00058666', 13, 23, 114308),
  ('The Apothecary Diaries S1', 'G3KHEVDJ7', 'S1', 1, 24, 161645),
  ('Tokyo Ghoul', 'G6NV7Z50Y', 'S00003544', 1, 12, 20605),
  ('Tokyo Ghoul Root A', 'G6NV7Z50Y', 'S00003545', 1, 12, 20850),
  ('Yu Yu Hakusho', 'GR9PKENW6', 'S1', 1, 112, 392),
  ('Re:Zero S2 part 1', 'GRGG9798R', 'S00171624', 1, 13, 108632),
  ('Re:Zero S2 part 2', 'GRGG9798R', 'S00171624', 14, 25, 119661),
  ('Black Butler S1', 'GYQ43P3E6', 'S1', 1, 24, 4898),
  ('Black Butler II', 'GYQ43P3E6', 'S2', 1, 12, 6707),
  ('Black Butler Book of Circus', 'GYQ43P3E6', 'S3', 1, 10, 20606),
  ('Black Butler Public School Arc', 'GYQ43P3E6', 'S4', 1, 11, 166715),
  ('Black Clover', 'GRE50KV36', 'S00363281', 1, 51, 97940),
  ('Black Clover', 'GRE50KV36', 'S00363282', 52, 102, 97940),
  ('Black Clover', 'GRE50KV36', 'S00363283', 103, 154, 97940),
  ('Black Clover', 'GRE50KV36', 'S00363284', 155, 170, 97940),
  ('Blue Lock S1', 'G4PH0WEKE', 'S00257766', 1, 24, 137822),
  ('Blue Lock U-20 S2', 'G4PH0WEKE', 'S00344677', 25, 38, 163146),
  ('Chainsaw Man', 'GVDHX8QNW', 'S00199349', 1, 12, 127230),
  ('Frieren S1', 'GG5H5XQX4', 'S00324919', 1, 28, 154587),
  ('Frieren S2', 'GG5H5XQX4', 'S00365545', 1, 10, 182255),
  ('Hell''s Paradise S1', 'GJ0H7Q5ZJ', 'S00198812', 1, 13, 128893),
  ('Kaiju No. 8 S1', 'GG5H5XQ7D', 'S00263871', 1, 12, 153288),
  ('Kaiju No. 8 S2 TV', 'GG5H5XQ7D', 'S00352541', 13, 23, 178754),
  ('Link Click S1', 'GP5HJ8E81', 'S00113950', 1, 11, 126403),
  ('Link Click S2 (2023)', 'GP5HJ8E81', 'S00303342', 1, 12, 136484),
  ('Samurai Champloo', 'G6WEK0026', 'S00003330', 1, 26, 205),
  ('The Great Cleric', 'GG5H5XQ24', 'S00117508', 1, 12, 155418)
), source_series(series_id) as (
  values ('G649PJ0JY'),('GY2P9ED0Y'),('GY5P48XEY'),('GYEXQKJG6'),
         ('GYQWNXPZY'),('G6ZJMGEXY'),('GRGGPG93R'),('GRDV0019R'),
         ('G6Q4Z8PQR'),('GRGG9798R'),('GDKHZEJ0K'),('G4PH0WXVJ'),
         ('GR49G9VP6'),('G3KHEVDJ7'),('G6NV7Z50Y'),('GR9PKENW6'),
         ('GMTE00194450'),('GYQ43P3E6'),('GRE50KV36'),('G4PH0WEKE'),
         ('GVDHX8QNW'),('GG5H5XQX4'),('GJ0H7Q5ZJ'),('GG5H5XQ7D'),
         ('GP5HJ8E81'),('G6WEK0026'),('GG5H5XQ24')
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
  from observations group by source_identifier
), proposed as (
  select g.*, m.label target_label, m.anilist_media_id,
         case when m.anilist_media_id = 97940 then g.source_number
              else g.source_number - m.first_number + 1 end local_episode_number,
         count(m.label) over (partition by g.source_identifier) range_matches
  from episode_groups g join source_series ss on g.series_id = ss.series_id
  left join media_spec m on g.series_id = m.series_id and g.source_season = m.source_season
    and g.source_number between m.first_number and m.last_number
  where g.source_identifier not in (
    'GP5HJ8E81|S00113950|E6', -- Link Click episode 5.5
    'GG5H5XQ7D|S00352541|E1', -- Hoshina's Day Off
    'GYQ43P3E6|M|E0'         -- Book of the Atlantic film
  )
)
select source_identifier, series_id, source_season, source_number,
       case when source_identifier = 'GYEXQKJG6|S00374284|E1' then 'held_special'
            when target_label is null then 'held_identity' else 'episode_candidate' end scope,
       target_label, anilist_media_id, local_episode_number,
       complete, observations, observed_versions,
       (series_variants = 1 and number_variants = 1 and range_matches <= 1) identity_consistent
from proposed
where complete
order by series_id, source_season, source_number nulls last, source_identifier;
