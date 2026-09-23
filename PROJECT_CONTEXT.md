# Marquee Project Context

## Current status note (2026-09-23)

Trakt's manual GitHub Actions import and replay succeeded. The workflow remains manual. Jikan v4 discontinued user anime-list reads in 2022, so the one-time MAL seed reads a private MAL XML export with stable MAL IDs. The Crunchyroll runner choice remains open: the original n8n plan below is a proposal, and no workflow is authored or activated without Dave's decision. The repo is the canonical cross-agent record; Dave's later instructions override earlier planning text.

Last updated: 2026-09-22
Owner: Dave DiBara
Status: Ingestion kickoff planning
Canonical future repo: `ddibara5/marquee`

## Read this first

Marquee is an iPhone-first PWA for TV, movies, and anime. Version 1 is tracking-first: episode check-ins, season progress, MAL-style statuses, a unified watchlist, detail pages, and where-to-watch. Recommendation features come after ingestion and tracking are proven.

The current phase is not the PWA. The current phase is to build a durable ingestion and identity layer that can survive source changes, mapping corrections, retries, and future UI work without rewriting the data model.

The GitHub repo is the canonical cross-agent source of truth once Dave creates it. Local Muse paths are working copies only and must not be the only copy of project scope or operating instructions.

## Product boundaries

### Version 1
- TV, movie, and anime tracking
- Episode watch history and season progress
- Show and movie statuses
- Ratings and scores
- Unified watchlist
- Detail pages
- Where-to-watch

### Version 1.1
- For You recommendations
- Taste profile
- Evidence-backed recommendation reasons
- Ask Marquee
- Shared media-agnostic taste engine with GameDeck
- Within-media duels only

### Not in kickoff
- PWA implementation
- Recommendation engine changes
- MAL write-back
- Social features
- Playback
- Changes to GameDeck ranking tables
- New Supabase project

## Architecture

Marquee shares GameDeck's Supabase project:

- Supabase project: `eiskobjlvxzwvucgpenk`
- Region: `us-east-1`
- Existing GameDeck data remains untouched
- All new Marquee database objects must use the `marquee_` prefix
- Shared Supabase Auth identity is intentional

Important: using the same Supabase Auth project gives both apps the same user identity, but cross-app browser session sharing is a separate PWA-phase concern. Do not assume a login session automatically transfers between two different app origins.

### High-level data flow

```text
Trakt --------\
MAL -----------\
Crunchyroll ----> Raw source records -> Identity and mapping -> Canonical Marquee data
AniList --------/        |                    |                       |
TMDb -----------/        v                    v                       v
                    Sync run log        Review queue           User tracking state
                         |                    |
                         +---- watermarks only advance after full success
```

## Source roles and precedence

### Trakt
Primary source for:
- Movie history
- Non-anime TV history
- Ratings
- Watchlist

Initial history, ratings, and watchlist are imported through the existing Trakt bridge. Ongoing sync must use the same canonical data contract and must report a heartbeat into Marquee sync telemetry.

### Crunchyroll
Primary ongoing source for:
- Anime episode watch activity

The integration uses unofficial Crunchyroll endpoints and must therefore be treated as a brittle adapter:
- Fail loudly on authentication or response-contract changes
- Preserve raw source records
- Never advance the watermark after a partial failure
- Never guess an identity match
- Cache successful mappings
- Do not call AniList again for already mapped stable Crunchyroll IDs

### AniList
Primary anime identity and relationship source for:
- Anime season entries
- Airing schedules
- Anime metadata
- Franchise relation graph

AniList relations are used to roll season entries into franchise-level shows. Auto-grouping must use explicit rules and a relation allowlist. Ambiguous or unusual graphs go to review rather than being guessed.

### MAL via Jikan
One-time seed source only:
- Statuses
- Scores

MAL is not an ongoing synchronization source and must never overwrite newer Marquee, Crunchyroll, or Trakt state after the seed import.

### TMDb
Future metadata and where-to-watch source:
- Posters and artwork
- General TV and movie metadata
- Watch provider availability

TMDb key provisioning can wait until the PWA phase.

## Canonical model

The original handoff's show -> season -> episode model remains the canonical episodic hierarchy, but movie support must be explicit.

Recommended core catalog:

- `marquee_titles`
  - Top-level canonical record
  - `media_type` is `show` or `movie`
  - Common title metadata lives here
- `marquee_shows`
  - One franchise-level show record
  - One-to-one with a `marquee_titles` show
- `marquee_movies`
  - One movie record
  - One-to-one with a `marquee_titles` movie
- `marquee_seasons`
  - Belongs to a show
  - Anime AniList entries generally map here
- `marquee_episodes`
  - Belongs to a season

This preserves the chosen franchise-level show model while giving statuses, watchlists, ratings, and recommendations a clean top-level target for both shows and movies.

## Identity and mapping

Do not use title text as the durable identity key.

Create a generalized source mapping layer, preferably `marquee_source_mappings`, with:
- source
- source entity type
- stable source ID
- canonical entity type
- canonical Marquee ID
- match method
- confidence or rule identifier
- manual lock flag
- timestamps
- optional notes

Titles may be stored for candidate generation and diagnostics, but stable source IDs are the mapping key whenever the source provides one.

Manual mappings and franchise overrides always win over automatic matching.

Recommended mapping precedence:

1. Explicit manual override
2. Existing locked source-ID mapping
3. Deterministic exact external-ID match
4. Approved deterministic mapping rule
5. Candidate search
6. Review queue

Step 5 must not silently become a production mapping when ambiguous.

## User tracking tables

Recommended user-state tables:

- `marquee_watch_history`
- `marquee_statuses`
- `marquee_ratings`
- `marquee_watchlist`

All user-state records must carry a Supabase user ID or equivalent owner scope, source provenance, and source timestamps where relevant.

### Cross-source duplicate rule

Trakt and Crunchyroll can both contain evidence of the same anime watch. Preserve the source observations in raw ingestion, but prevent the canonical history from double-counting the same logical viewing event.

The normalization layer must define deterministic overlap handling before the first full import. Crunchyroll is the preferred source for ongoing anime episode history.

### Status and rating rule

Do not conflate status and rating.

MAL scores and Trakt ratings need a dedicated rating model. MAL status data can seed canonical status only when no higher-precedence state exists.

## Operational tables

### `marquee_ingest_raw`
Append or idempotently store fetched source payloads before normalization.

Minimum fields:
- source
- source record ID when available
- fetched_at
- sync_run_id
- payload JSON
- payload hash or dedupe key
- normalization status

Purpose:
- Reprocess data after mapping fixes without refetching
- Diagnose source changes
- Preserve provenance
- Avoid repeating a GameDeck-style unmatched-title recovery problem

### `marquee_mapping_review`
Explicit queue for unresolved or ambiguous identity work.

Minimum fields:
- source
- stable source ID
- source title
- candidate matches
- reason
- status
- resolved mapping
- resolution notes
- created_at
- resolved_at

### `marquee_sync_state`
Current checkpoint only.

Minimum fields:
- source
- watermark or cursor
- last_attempt_at
- last_success_at
- last_error
- consecutive_failures

### `marquee_sync_runs`
Append-only execution history.

Minimum fields:
- source
- started_at
- completed_at
- status
- fetched_count
- inserted_count
- updated_count
- skipped_count
- unmapped_count
- error_count
- workflow or execution ID
- error summary

`marquee_sync_state` answers "where should the next run begin?"
`marquee_sync_runs` answers "what actually happened?"

## Watermark invariant

A source watermark advances only after all required persistence stages for that run succeed.

If mapping or normalization produces unresolved records, the raw records and review-queue entries must be safely persisted before the run can be considered successful.

A failed or partially written run must be retryable without duplicate canonical records.

## Idempotency requirements

Every source adapter must pass these tests:

1. First run imports expected records.
2. Running the same input again creates no duplicate canonical records.
3. Replaying a previously stored raw payload is safe.
4. Failed runs do not advance their watermark.
5. A corrected mapping can reprocess affected raw records without refetching.
6. Existing manual overrides are never replaced by automatic mapping.
7. Existing metadata is preserved unless the incoming source is authoritative for that field.

## Shared Supabase safety boundary

Because Marquee and GameDeck share one Supabase project, Marquee migrations must be more narrowly scoped than some historical GameDeck migrations.

Never use Marquee migrations to:
- Revoke privileges across every table in `public`
- Drop or recreate policies across every table in `public`
- Loop over unrelated public-schema objects
- Change global default privileges without an explicit reviewed reason
- Rename, drop, or rewrite GameDeck objects
- Modify `game_ranks` or `rank_comparisons` during kickoff

Every grant, policy, index, function, trigger, view, and table created for Marquee should be explicitly named and Marquee-scoped.

After every Marquee migration:
- Anonymous users cannot read private Marquee data
- The authorized user can read and modify only intended Marquee user-state data
- Service-role ingestion still works
- GameDeck access and RLS behavior are unchanged
- Supabase security and performance advisors show no new relevant errors

## Auth model

Use `auth.uid()`-based user scoping for Marquee user-state data rather than copying GameDeck's fixed-email helper pattern into new tables.

Catalog data may be shared across the authenticated Marquee user, while watch history, status, ratings, and watchlist remain user-scoped.

The same Supabase user identity should eventually work in GameDeck and Marquee. Cross-origin single-session behavior is a separate frontend implementation task and is not part of ingestion kickoff.

## n8n Crunchyroll workflow

Canonical workflow JSON lives in the repo.

Recommended steady-state flow:

```text
Daily Schedule
  -> authenticate
  -> start sync_run
  -> fetch incremental history
  -> persist raw source records
  -> look up stable source-ID mappings
  -> resolve only new unmapped IDs
       -> cached mapping
       -> AniList fallback with throttling
       -> review queue if ambiguous
  -> normalize
  -> transactional/idempotent upsert
  -> finish sync_run
  -> advance watermark
```

Failure path:
- record failed sync run
- preserve diagnostic error
- do not advance watermark
- notify loudly
- do not silently emit an empty success

The canonical repo export must never contain Crunchyroll credentials or usable secret tokens.

## AniList usage rule

AniList lookups happen only on cache misses or explicit remapping.

The workflow must:
- respect returned rate-limit headers
- back off on HTTP 429
- batch or throttle bootstrap work
- avoid a separate relation lookup for every daily history item
- persist resolved AniList IDs so normal daily runs are cheap

## Trakt sync

ChatGPT authors a portable sync script. Muse executes it through the existing bridge.

The script must:
- be configuration-driven
- take bridge location and secrets from environment or secure runtime configuration
- paginate all endpoints
- preserve stable Trakt IDs and available TMDb/IMDb IDs
- import history, ratings, and watchlist
- write sync telemetry
- be idempotent
- not depend on hard-coded local filesystem secrets

For ongoing sync, the transport can remain the existing bridge during v1, but the Marquee data contract must not depend on that bridge so the transport can be replaced later without a schema rewrite.

## MAL import

One-time script only.

The script must:
- preserve MAL IDs
- map MAL entries to canonical titles or anime seasons
- import statuses as seed state only
- import scores into the rating model
- treat score 0 or equivalent as unrated
- preserve the original source payload for audit/reprocessing
- never become a scheduled workflow

## Collaboration model

Dave creates the GitHub repo.

For any agent editing the repo:
1. Read remote `main` HEAD and record `BASE_SHA`.
2. Inspect canonical docs and current migrations before editing.
3. Work on top of `BASE_SHA`.
4. Never force-push.
5. Build, lint, validate, or parse generated artifacts before push when possible.
6. If `main` moved, reapply onto the new HEAD.
7. Report final commit SHA and the exact files changed.
8. Do not call anything live until the applying operator verifies it.

For Marquee specifically:
- ChatGPT is the primary author of repo artifacts.
- Muse is the designated operator for applying Supabase changes, wiring secrets, using the Trakt bridge, and tuning real-history mappings.
- This is an operating boundary, not a claim that other connectors are technically unavailable.
- Any n8n activation still requires Dave's explicit approval.

## Repo layout

Recommended initial structure:

```text
/
  PROJECT_CONTEXT.md
  README.md
  docs/
    SCOPE.md
    INGESTION_PLAN.md
    SOURCE_OF_TRUTH.md
    RUNBOOK.md
  supabase/
    migrations/
    verification/
  n8n/
    marquee-crunchyroll-sync.json
  scripts/
    trakt-sync/
    mal-import/
  fixtures/
    crunchyroll/
    trakt/
    mal/
  tests/
```

Do not leave the only copy of scope in a Muse-local `~/workspace/...` path. Commit the canonical scope into `docs/SCOPE.md`.

## Kickoff execution plan

### Phase 0: Repo and contracts
- Dave creates `ddibara5/marquee`
- Add this project context
- Move the canonical scope into `docs/SCOPE.md`
- Add source-of-truth matrix
- Add representative sanitized fixtures from each source
- Define schema invariants and acceptance queries

### Phase 1: Database foundation
- Author additive `marquee_*` migrations
- Add movie support
- Add ratings
- Add stable source mappings
- Add raw ingestion
- Add mapping review queue
- Add sync state and append-only sync runs
- Add user-scoped RLS
- Add verification SQL
- Confirm migrations contain no global public-schema changes

### Phase 2: Import adapters
- Author Trakt sync script
- Author MAL one-time import
- Unit-test normalization against fixtures
- Verify pagination, retry, and idempotency behavior

### Phase 3: Crunchyroll workflow
- Author n8n workflow JSON
- Validate JSON and graph structure
- Keep secrets out of repo
- Build explicit failure and review paths
- Implement AniList throttling and mapping cache

### Phase 4: Apply and bootstrap
Muse:
- applies migrations
- wires credentials
- imports workflow inactive
- runs Trakt import
- runs MAL import
- performs first manual Crunchyroll bootstrap
- verifies row counts and sync telemetry

If Dave has already approved activation, the workflow may be enabled only after the manual run passes.

### Phase 5: Mapping tuning
Muse owns:
- unresolved Crunchyroll mappings
- franchise grouping corrections
- manual override creation
- reruns from stored raw records

Dave adjudicates only truly ambiguous items.

### Phase 6: Acceptance and freeze
Produce a completion report with:
- row counts by table
- source counts
- mapped automatically
- mapped manually
- unresolved
- duplicate checks
- current watermarks
- last successful sync runs
- RLS verification
- GameDeck regression verification
- advisor results
- known source limitations

After this report, freeze the ingestion contract and begin PWA planning separately.

## Definition of done

Kickoff is complete when:

- All required `marquee_*` tables and policies exist
- Movies are represented explicitly
- Ratings are represented explicitly
- Every imported source record retains provenance
- Stable source IDs drive mapping
- Trakt history, ratings, and watchlist are imported
- MAL is imported once as seed data
- Crunchyroll workflow completes a real manual bootstrap
- A second equivalent run is idempotent
- Failed-run watermark behavior is verified
- Ambiguous mappings appear in a review queue instead of being guessed
- Mapping tuning is complete or remaining ambiguities are explicitly accepted
- Ongoing Trakt and Crunchyroll sync cadences are documented
- GameDeck behavior is unchanged
- Secrets are absent from the repo
- Completion report is written
- ChatGPT hands mapping tuning and live-source cleanup back to Muse

## Deferred design note for v1.1

Do not modify `game_ranks` or `rank_comparisons` during ingestion kickoff.

Those current GameDeck tables are directly foreign-keyed to GameDeck games. The decision to share the taste engine remains valid, but the additive compatibility design for non-game media should be handled as a dedicated v1.1 migration after Marquee's canonical media IDs are stable.
