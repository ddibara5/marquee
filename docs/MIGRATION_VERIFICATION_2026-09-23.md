# Migration verification — 2026-09-23

Project: `eiskobjlvxzwvucgpenk` (`GameDeck`, `us-east-1`, PostgreSQL 17). Dave explicitly authorized ChatGPT to apply the Marquee ingestion migration.

## Applied versions

| Version | Migration | Result |
| --- | --- | --- |
| `20260923151159` | `marquee_ingestion_foundation` | 16 tables, 21 initial policies, source identity and run telemetry. |
| `20260923152134` | `marquee_access_and_fk_indexes` | Seven service-only deny policies and ten reverse FK indexes. |

Both operations returned success and were read back from the migration ledger. The live schema has 16 `marquee_*` tables and 28 Marquee policies. Catalog and run tables currently have zero rows.

## Validation

- Ran the initial migration in a disposable PostgreSQL runtime before production. All 85 statements completed. Two fixture users demonstrated owner-only status reads/writes, cross-owner insert denial, anonymous grant denial and service-role insert grants.
- Ran the follow-up in the same disposable runtime. Verified seven deny policies and ten indexes.
- In production, all 16 Marquee tables have RLS enabled, anonymous SELECT is denied, and service-role INSERT is granted. Authenticated SELECT is granted only to catalog and intended user-state tables; operational tables remain service-only.
- The GameDeck `games`, `play_events`, `game_ranks`, and `rank_comparisons` access grants, RLS flags and policies matched the before snapshot. Their row counts remained `518`, `552`, `53`, and `154` across the initial migration.
- No PWA, source importer or n8n workflow was changed or run.

## Advisors and limits

Security advisors have no new Marquee findings after the follow-up. Existing GameDeck/Auth findings remain unchanged. The performance advisor reports two composite foreign keys on `marquee_shows` and `marquee_movies` as unindexed, although their `title_id` primary keys lead those lookups; adding duplicate composite indexes is deferred. New Marquee indexes appear as unused while the tables are empty.

Production has one Auth user, so a two-user live RLS probe was not run. The disposable two-user test and production grant/policy inspection cover the intended access model; a real signed-in app flow remains for the PWA phase. The ingestion watermark, replay, mapping and duplicate rules remain unverified with real source data until Phase 2/3 imports.
