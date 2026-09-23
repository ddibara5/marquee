# Ingestion schema and contract

Status: Phase 1 schema applied 2026-09-23 as migrations `20260923151159` and `20260923152134`. All new objects are `marquee_*` in `public`. No existing GameDeck object or global default privilege was changed.

Update 2026-09-23: Trakt import and replay succeeded. Dave's anime statuses and scores came from anilist.co through MyAniList for iOS; no MAL account exists, and the unused MAL importer was removed. The AniList import and replay also succeeded: 50 statuses, 33 ratings and 50 stable media mappings with no open AniList review. AniList did not seed dated episode watch events. The Crunchyroll runner choice is open; the n8n reference in the project context remains a proposal, not an approved activation.

The forward, Marquee-only migration allowing `source='anilist'` in `marquee_statuses` and `marquee_ratings` was applied and verified before the seed. Do not rewrite the applied migration or touch GameDeck. Leave the historical unused MAL values in the applied schema until a separately reviewed cleanup.

The applied migration and importer live at `supabase/migrations/20260923183118_marquee_anilist_user_state_source.sql` and `scripts/anilist-import/`. The script requests scores on AniList's fixed 10-point decimal scale and retains the raw entry. Dave approved the public-list import for `Daveywavey9`. Muse reviewed the 45 initially ambiguous entries, wrote manual mappings, then replayed the import to zero unresolved entries. The importer is a one-time list seed, not an ongoing episode history source.

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

### Agreed execution order as of 2026-09-23

1. Establish Trakt credential continuity, including the expiring access token and flagged client-secret rotation, then schedule and verify the existing idempotent sync. Rotate the flagged Supabase database password through the operator without committing secrets. The manual Trakt import already works; this step makes it ongoing.
2. Test Crunchyroll history access read-only. Establish pagination, oldest available event, timestamps, stable episode IDs, account/profile scope and whether the returned history is complete. Do not promise lifetime coverage before checking. Select the extraction method and runner after this evidence; n8n has not been conclusively ruled out in this repo plan.
3. Backfill all accessible Crunchyroll episode history. Preserve raw observations, map stable IDs to the reviewed AniList catalog, send ambiguity to review, check Trakt overlap with real timestamps, and verify replay before committing a success checkpoint.
4. Start incremental Crunchyroll sync with a replay overlap at the backfill boundary. Verify fresh events, no duplicates, failure behavior, source provenance and an unchanged GameDeck baseline. Do not activate a schedule or live n8n workflow without Dave's authorization.

Trakt token refresh and a full Marquee-token database replay succeeded on 2026-09-23. The daily GitHub Actions schedule is set for 11:17 UTC; verify the first scheduled execution before treating Trakt as ongoing. AniList is complete as a one-time status and score seed, and MAL is out of scope. Next: the manual, read-only [Crunchyroll history probe](../scripts/crunchyroll/README.md) checks coverage and response shape without DB access or raw record logging. Its GitHub Actions runner is only for this probe; the ongoing Crunchyroll runner remains undecided. Only after the ongoing feeds are proven should PWA work begin.

Trakt: paginate history, ratings and watchlist; retain Trakt, TMDb and IMDb IDs, original timestamps and run heartbeat. AniList account: fetch the complete anime list, retain stable media/list-entry IDs and source score format, seed statuses and scores with source precedence. Crunchyroll: cache mapped IDs, throttle AniList on cache misses, back off on HTTP 429, and fail loudly on contract changes. Credentials are supplied at runtime; no live Crunchyroll workflow is authorized yet.

Phase 2 Trakt script: [`scripts/trakt-sync/README.md`](../scripts/trakt-sync/README.md) documents the Python implementation, direct OAuth transport, reviewed non-anime TV ID gate and private Postgres runner requirements. Its first live import and replay succeeded on 2026-09-23. The bridge interface has not been provided; source access can be swapped without changing the catalog contract.
