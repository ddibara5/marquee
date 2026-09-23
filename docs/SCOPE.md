# Scope — ingestion kickoff

This is a working scope summary derived from [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md), the sole canonical project context. Dave's later instructions can override it. A separate Muse scope document is not required.

## Product

Marquee tracks shows, movies, anime seasons and episodes. V1 includes episode check-ins, season progress, statuses, ratings, a unified watchlist, title pages and where-to-watch. Recommendation and taste features follow in v1.1.

## This release

1. Bootstrap canonical docs and additive Marquee-only database migrations. **Completed 2026-09-23.**
2. Define stable source mappings, raw record preservation, review queue, run telemetry and checkpoints. **Schema completed; import behavior pending.**
3. Verify role access, integrity and an unchanged GameDeck baseline before and after application. **Completed for empty Marquee tables; replay and source-data checks await imports.**

## Next releases

- Trakt importer, one-time MAL/Jikan seed, sanitized source fixtures and replay tests.
- Crunchyroll n8n workflow with AniList cache misses and a manual bootstrap.
- Mapping corrections and real-history validation by Muse.

No PWA, recommendations, MAL write-back, social features, playback, GameDeck rank changes, or live workflow changes belong to this release.

## Operating boundary

ChatGPT authors repo files; Dave explicitly authorized ChatGPT to validate and apply the two kickoff migrations on 2026-09-23. Muse remains responsible for configuring secrets and the Trakt bridge and tuning real-history mappings. The Crunchyroll workflow requires explicit approval before activation.
