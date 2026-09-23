# Marquee ingestion foundation

Marquee is an iPhone-first TV, movie, and anime tracker. This repository draft covers the ingestion and identity foundation only. The PWA and recommendations are deferred.

[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the sole canonical project context, copied from the ChatGPT Project attachment. Dave's later instructions can override it. The [scope summary](docs/SCOPE.md), [schema contract](docs/INGESTION_PLAN.md), and [source ownership](docs/SOURCE_OF_TRUTH.md) are implementation documents derived from that context.

The migrations under `supabase/migrations/` were applied to the shared GameDeck Supabase project `eiskobjlvxzwvucgpenk` on 2026-09-23. Read [RUNBOOK.md](docs/RUNBOOK.md) and the [verification report](docs/MIGRATION_VERIFICATION_2026-09-23.md) before subsequent changes. No source credentials belong in this repository.

Status on 2026-09-23: Phase 0 and Phase 1 schema are live and verified. Trakt's manual import and replay succeeded ([first run](https://github.com/ddibara5/marquee/actions/runs/35890598381), [replay](https://github.com/ddibara5/marquee/actions/runs/35896718778)). Dave confirmed that his anime list is on anilist.co through MyAniList for iOS; he has no MAL account, so the unused MAL importer was removed. Next is the AniList list seed, then ongoing Crunchyroll history. The Crunchyroll runner choice remains open, with n8n still proposed and no live workflow activated. No PWA or recommendation engine work has started.
