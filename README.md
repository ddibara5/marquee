# Marquee ingestion foundation

Marquee is an iPhone-first TV, movie, and anime tracker. This repository draft covers the ingestion and identity foundation only. The PWA and recommendations are deferred.

[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the sole canonical project context, copied from the ChatGPT Project attachment. Dave's later instructions can override it. The [scope summary](docs/SCOPE.md), [schema contract](docs/INGESTION_PLAN.md), and [source ownership](docs/SOURCE_OF_TRUTH.md) are implementation documents derived from that context.

The migrations under `supabase/migrations/` were applied to the shared GameDeck Supabase project `eiskobjlvxzwvucgpenk` on 2026-09-23. Read [RUNBOOK.md](docs/RUNBOOK.md) and the [verification report](docs/MIGRATION_VERIFICATION_2026-09-23.md) before subsequent changes. No source credentials belong in this repository.

Status on 2026-09-23: Phase 0 and Phase 1 schema are live and verified. Catalog and user-state tables are empty; no source importer or n8n workflow has been run.
