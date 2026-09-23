# Migration runbook

The migration has not been applied.

1. Read remote `ddibara5/marquee@main` HEAD and record `BASE_SHA` before each edit. Inspect its existing files and build on the latest HEAD. Never force-push.
2. Review `docs/INGESTION_PLAN.md`, the migration, and the current GameDeck security baseline. Confirm `marquee_*` names are unused and check existing `auth.users` behavior.
3. Muse applies the versioned SQL in a controlled migration. The migration deliberately avoids global grants, default privilege changes, GameDeck tables and all existing policies.
4. Run `supabase/verification/01_structure_and_regressions.sql` before and after; compare the exact GameDeck snapshots. Run `02_role_access.sql` as a read-only policy check and `04_disposable_role_probe.sql` with two disposable Auth users in an isolated database. Run `03_integrity_and_replay.sql` after import. Check security and performance advisors.
5. If any verification fails, stop imports, record the error and repair with a separate Marquee-scoped forward migration. Do not roll back shared project tables.

Importer authors must put the final successful run update and watermark update in one transaction after persistence verification. A failed run keeps the previous watermark. Unmapped identities are written to raw and review before successful completion. Source credentials stay in a secure runtime.

Operator handoff: report applied version, table counts, role verification, GameDeck baseline diff, advisors, unmapped count, replay outcome and current watermarks. Do not call a repo commit or unapplied SQL live.
