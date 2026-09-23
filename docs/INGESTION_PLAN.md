# Ingestion schema and contract

Status: Phase 1 schema applied 2026-09-23 as migrations `20260923151159` and `20260923152134`. All new objects are `marquee_*` in `public`. No existing GameDeck object or global default privilege was changed.

Update 2026-09-23: Trakt import and replay succeeded. Dave's anime statuses and scores live on anilist.co through MyAniList for iOS; no MAL account exists, and the unused MAL importer was removed. The next adapter seeds the AniList list using stable media IDs and preserves account score format. The Crunchyroll runner choice is open; the n8n references below remain proposed architecture.

Before the AniList seed can write user state, author and verify a forward, Marquee-only migration allowing `source='anilist'` in `marquee_statuses` and `marquee_ratings`. Their applied check constraints currently allow MAL but exclude AniList. Do not rewrite the applied migration or touch GameDeck. Determine the actual AniList score format and list visibility before writing the adapter. Leave the historical unused MAL values in the applied schema until there is a separately reviewed cleanup.

| Layer | Tables | Key invariant |
| --- | --- | --- |
| Catalog | `marquee_titles`, `marquee_shows`, `marquee_movies`, `marquee_seasons`, `marquee_episodes` | One top-level title is a show or movie; seasons belong to shows and episodes to seasons. |
| User state | `marquee_watch_history`, `marquee_watch_history_sources`, `marquee_statuses`, `marquee_ratings`, `marquee_watchlist` | Each row belongs to an `auth.users` ID; history observations from two providers can point to one canonical event. |
| Identity | `marquee_source_mappings`, `marquee_franchise_overrides`, `marquee_mapping_review` | `(source, source_entity_type, source_id)` has one canonical target. Manual locks win; only one open review per source identity. |
| Operations | `marquee_ingest_raw`, `marquee_sync_state`, `marquee_sync_runs` | Raw dedupe by `(scope, source, entity type, dedupe key)`; checkpoint is independent of run telemetry. |

## Choices to preserve

- UUID canonical IDs, text stable source IDs. Provider IDs never become primary keys. Catalog IDs are immutable once assigned.
- `marquee_source_mappings` uses one typed target FK column at a time. This enforces real FK integrity despite multiple canonical entity types.
- Anime AniList entries normally map to `season`; franchise overrides explicitly map a stable source identity to a `show` title. Episode number and season number can be unknown; source IDs still prevent duplicates.
- Statuses and ratings accept either a title or a season target. This retains distinct AniList anime season scores. Watchlist stays at title level.
- Canonical history stores one row per logical viewing and a stable logical key. `marquee_watch_history_sources` links every source event by stable ID. Raw payloads remain available even before mapping.
- Raw payloads may be re-fetched and hashed; `dedupe_key` is stable across replays, while a changed payload updates the stored version during a future adapter phase. Sensitive tokens and request headers must never be stored in payload.
- Sync runs are one row per execution: an initial `running` row can transition once to a terminal status. Ingestion cannot delete run rows; an Auth user deletion may cascade to remove personal records.
- `scope_key` is `catalog` for shared metadata or the owner UUID as text for private fetches. It is checked against `user_id`.
- All `marquee_*` tables have RLS enabled. Catalog SELECT is available to authenticated users; user state uses `(select auth.uid()) = user_id`; operational and identity tables are service-role only. Anonymous has no grants. `service_role` owns ingestion access.

## Adapter transaction rule

Fetch pages completely, persist raw records, resolve mappings or review entries, upsert canonical rows idempotently, then mark the run successful and advance the checkpoint in **one final database transaction**. Any future Crunchyroll runner must supply this atomicity, through a Marquee-scoped RPC or an equivalent transactional adapter. A run with an unexpected page shape, missing page, failed persistence or incomplete count remains failed without a checkpoint advance. A review item is a valid terminal normalization outcome only after raw and review writes succeed. Replays use stable source IDs, dedupe keys and logical event keys.

Before the first real import, validate the Crunchyroll/Trakt overlap window with actual source timestamps. Do not guess that window in this schema migration.

## Phase 2 and 3 gates

Trakt: paginate history, ratings and watchlist; retain Trakt, TMDb and IMDb IDs, original timestamps and run heartbeat. AniList account: fetch the complete anime list, retain stable media/list-entry IDs and source score format, seed statuses and scores with source precedence. Crunchyroll: cache mapped IDs, throttle AniList on cache misses, back off on HTTP 429, and fail loudly on contract changes. Credentials are supplied at runtime; no live Crunchyroll workflow is authorized yet.

Phase 2 Trakt script: [`scripts/trakt-sync/README.md`](../scripts/trakt-sync/README.md) documents the Python implementation, direct OAuth transport, reviewed non-anime TV ID gate and private Postgres runner requirements. Its first live import and replay succeeded on 2026-09-23. The bridge interface has not been provided; source access can be swapped without changing the catalog contract.
