# Scope — ingestion kickoff

This is a working scope summary derived from [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md), the sole canonical project context. Dave's later instructions can override it. A separate Muse scope document is not required.

## Product

Marquee tracks shows, movies, anime seasons and episodes. V1 includes episode check-ins, season progress, statuses, ratings, a unified watchlist, title pages and where-to-watch. Recommendation and taste features follow in v1.1.

## This release

1. Bootstrap canonical docs and additive Marquee-only database migrations. **Completed 2026-09-23.**
2. Define stable source mappings, raw record preservation, review queue, run telemetry and checkpoints. **Schema completed; Trakt import and replay verified.**
3. Verify role access, integrity and an unchanged GameDeck baseline before and after application. **Completed for the schema; Muse reported unchanged GameDeck row counts after Trakt import.**

## Next releases

- Trakt import and replay completed on 2026-09-23. Next, settle credential refresh and schedule ongoing Trakt sync before the current token expires.
- Dave's anilist.co list seed and replay completed: 50 statuses, 33 ratings and no open AniList reviews. MyAniList on iOS is his client. There is no MAL import. AniList did not seed dated episode watch events.
- Test read-only access to Crunchyroll history, document its oldest available event and source identity fields, then backfill the accessible history with reviewed mappings.
- Start Crunchyroll incremental sync after backfill with a replay overlap, idempotency checks and a watermark that advances only after all required writes succeed. The runner choice remains open, including whether to use n8n.
- Recheck GameDeck behavior and counts after the new ingestion work. Mapping corrections and real-history validation remain with Muse.

No PWA, recommendations, AniList write-back, social features, playback, GameDeck rank changes, or live workflow changes belong to this release.

## Operating boundary

ChatGPT authors repo files; Dave explicitly authorized ChatGPT to validate and apply the two kickoff migrations on 2026-09-23. Muse remains responsible for configuring secrets and the Trakt bridge and tuning real-history mappings. The Crunchyroll workflow requires explicit approval before activation.
