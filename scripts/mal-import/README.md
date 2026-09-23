# One-time MAL anime status and score seed

**Parked 2026-09-23:** Dave confirmed that his current anime tracking data is on anilist.co through the MyAniList iOS client, not a confirmed MAL list. Do not run this script against his current data. Build a dedicated AniList list seed. Retain this importer only if a separate MAL export is later identified.

Jikan v4 [discontinued its user anime-list endpoint in 2022](https://github.com/jikan-me/jikan-rest/blob/master/storage/api-docs/api-docs.json). A username cannot supply the list through that endpoint. This importer reads an XML or XML.gz export from [MyAnimeList's export page](https://myanimelist.net/panel.php?go=export) instead. Jikan is not needed to read the private status and score fields. No network calls, MAL write-back, or scheduler are involved.

The operator supplies the export privately; it contains personal list data and must not be committed. The only committed fixture, `fixtures/mal/list.xml`, is synthetic. The importer uses `series_animedb_id` as the stable key and expects an existing `marquee_source_mappings` row `(source='mal', source_entity_type='anime', source_id=<MAL ID>)` pointing to an anime season or show. It never resolves by title. Unknown IDs retain their raw payload in `marquee_ingest_raw` and get an open `marquee_mapping_review` row. After a verified mapping is created, replay the **same export** to seed the status and score. A score of zero is unrated. Any existing status or rating, including an older MAL seed, wins over the import. This is a seed, not a sync.

Requirements: Python 3.11+, `psycopg[binary]==3.3.6` from `scripts/trakt-sync/requirements.txt`, the existing Supabase `auth.users` UUID, and a secure `MARQUEE_DATABASE_URL` for the IPv4 session pooler or direct Postgres (session advisory lock required). The applying operator checks the target project is `eiskobjlvxzwvucgpenk` before writing. Never put a database password or an actual export in Git or chat.

```sh
python scripts/mal-import/mal_import.py --input /private/path/animelist.xml.gz --user-id EXISTING_AUTH_UUID --dry-run
python -m unittest discover -s tests -p 'test_mal*.py'
# After the operator reviews the input and target project:
python scripts/mal-import/mal_import.py --input /private/path/animelist.xml.gz --user-id EXISTING_AUTH_UUID
```

The write uses a per-user lock and one transaction for raw records, review, seeds, succeeded run and checkpoint. A failed run is recorded separately and leaves the previous checkpoint intact. The identical export can be replayed after verified mappings; a different export is refused after the first successful seed to prevent newer edits from being overwritten. Report `fetched`, `inserted`, `skipped`, `unmapped` and the review IDs after running. `inserted` counts status and rating rows, so it can exceed the number of anime entries. An all-unmapped run is a valid preservation step, but no status or rating is seeded until mappings exist.
