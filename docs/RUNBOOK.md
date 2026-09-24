# Migration runbook

Current Crunchyroll operations (2026-09-24): the reviewed historical undated import is complete. The incremental n8n transaction migrations `20260924200000` and `20260924201000` are applied. An [inactive n8n workflow and credential setup runbook](../scripts/crunchyroll/N8N_INCREMENTAL.md) replace the older runner proposal below. Its Crunchyroll credential still has a placeholder; the manual run and daily schedule have not started. Use that runbook for current activation and stop conditions.

The foundation and scoped advisor follow-up were applied 2026-09-23 as migration versions `20260923151159` and `20260923152134`. Read the [verification report](MIGRATION_VERIFICATION_2026-09-23.md) before imports.

1. Read remote `ddibara5/marquee@main` HEAD and record `BASE_SHA` before each edit. Inspect its existing files and build on the latest HEAD. Never force-push.
2. Review `docs/INGESTION_PLAN.md`, the migration, and the current GameDeck security baseline. Confirm `marquee_*` names are unused and check existing `auth.users` behavior.
3. The applying operator applies versioned SQL through the migration ledger. Both kickoff migrations avoided global grants, default privilege changes, GameDeck tables and existing policies.
4. Run `supabase/verification/01_structure_and_regressions.sql` before and after; compare the exact GameDeck snapshots. Run `02_role_access.sql` as a read-only policy check and `04_disposable_role_probe.sql` with two disposable Auth users in an isolated database. Run `03_integrity_and_replay.sql` after import. Check security and performance advisors. This was completed for the empty schema on 2026-09-23; real source-data checks remain.
5. If any verification fails, stop imports, record the error and repair with a separate Marquee-scoped forward migration. Do not roll back shared project tables.

Importer authors must put the final successful run update and watermark update in one transaction after persistence verification. A failed run keeps the previous watermark. Unmapped identities are written to raw and review before successful completion. Source credentials stay in a secure runtime.

Trakt's first import and replay completed 2026-09-23. Dave has no MAL account; AniList is his anime list source. The MAL importer was removed. The AniList seed and replay completed on 2026-09-23 with 50 mapped entries, 50 statuses, 33 ratings and zero open AniList reviews. The Crunchyroll runner choice remains open; n8n is a proposal, not an approved activation. The existing migration includes unused MAL values; removing them from a shared live project is outside this scoped cleanup.

The AniList migration `20260923183118_marquee_anilist_user_state_source.sql` and verification `05_anilist_user_state_source.sql` were applied and checked before the import. The [AniList importer notes](../scripts/anilist-import/README.md) document how the one-time seed can be replayed after verified corrections. Do not confuse its list statuses and scores with dated episode watch history. Next, establish Trakt credential refresh and an ongoing schedule; then validate Crunchyroll history access, backfill accessible episodes, and start incremental sync with an overlap. Keep schedules manual until the applying operator verifies and Dave authorizes activation.

Operator handoff: report applied version, table counts, role verification, GameDeck baseline diff, advisors, unmapped count, replay outcome and current watermarks. Do not call a repo commit or unapplied SQL live.
