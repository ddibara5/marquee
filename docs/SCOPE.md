# Scope — ingestion kickoff

Derived from the canonical `PROJECT_CONTEXT.md` supplied 2026-09-22. The separately mentioned `marquee-scope.md` was not available for this kickoff; reconcile it when available.

## Product

Marquee tracks shows, movies, anime seasons and episodes. V1 includes episode check-ins, season progress, statuses, ratings, a unified watchlist, title pages and where-to-watch. Recommendation and taste features follow in v1.1.

## This release

1. Bootstrap canonical docs and an additive Marquee-only database migration.
2. Define stable source mappings, raw record preservation, review queue, run telemetry and checkpoints.
3. Verify role access, integrity and an unchanged GameDeck baseline before and after application.

## Next releases

- Trakt importer, one-time MAL/Jikan seed, sanitized source fixtures and replay tests.
- Crunchyroll n8n workflow with AniList cache misses and a manual bootstrap.
- Mapping corrections and real-history validation by Muse.

No PWA, recommendations, MAL write-back, social features, playback, GameDeck rank changes, or live workflow changes belong to this release.

## Operating boundary

ChatGPT authors repo files. Muse applies migration, configures secrets and Trakt bridge, and tunes real-history mappings. The ingestion workflow requires explicit approval before activation. No live Supabase mutation is part of this draft.
