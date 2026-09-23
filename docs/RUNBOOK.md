# Migration runbook

The foundation and scoped advisor follow-up were applied 2026-09-23 as migration versions `20260923151159` and `20260923152134`. Read the [verification report](MIGRATION_VERIFICATION_2026-09-23.md) before imports.

1. Read remote `ddibara5/marquee@main` HEAD and record `BASE_SHA` before each edit. Inspect its existing files and build on the latest HEAD. Never force-push.
2. Review `docs/INGESTION_PLAN.md`, the migration, and the current GameDeck security baseline. Confirm `marquee_*` names are unused and check existing `auth.users` behavior.
3. The applying operator applies versioned SQL through the migration ledger. Both kickoff migrations avoided global grants, default privilege changes, GameDeck tables and existing policies.
4. Run `supabase/verification/01_structure_and_regressions.sql` before and after; compare the exact GameDeck snapshots. Run `02_role_access.sql` as a read-only policy check and `04_disposable_role_probe.sql` with two disposable Auth users in an isolated database. Run `03_integrity_and_replay.sql` after import. Check security and performance advisors. This was completed for the empty schema on 2026-09-23; real source-data checks remain.
5. If any verification fails, stop imports, record the error and repair with a separate Marquee-scoped forward migration. Do not roll back shared project tables.

Importer authors must put the final successful run update and watermark update in one transaction after persistence verification. A failed run keeps the previous watermark. Unmapped identities are written to raw and review before successful completion. Source credentials stay in a secure runtime.

Trakt's first import and replay completed 2026-09-23. The MAL importer at `scripts/mal-import/` is a one-time private XML seed; verify existing MAL ID mappings before execution and rerun the identical export after approved mappings are added. The Crunchyroll runner choice remains open; n8n is a proposal, not an approved activation.

Operator handoff: report applied version, table counts, role verification, GameDeck baseline diff, advisors, unmapped count, replay outcome and current watermarks. Do not call a repo commit or unapplied SQL live.
