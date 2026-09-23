# Marquee ingestion foundation

Marquee is an iPhone-first TV, movie, and anime tracker. This repository draft covers the ingestion and identity foundation only. The PWA and recommendations are deferred.

Start with [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), [scope](docs/SCOPE.md), [schema contract](docs/INGESTION_PLAN.md), and [source ownership](docs/SOURCE_OF_TRUTH.md).

The migration under `supabase/migrations/` is **authored, not applied**. The shared GameDeck Supabase project is `eiskobjlvxzwvucgpenk`. Muse is the applying operator. Read [RUNBOOK.md](docs/RUNBOOK.md) before any application. No source credentials belong in this repository.

Status on 2026-09-23: Phase 0 and Phase 1 artifacts are authored in the repository. The database migration is unapplied and awaits operator review and verification.
