# AniList one-time list seed

The source is Dave's **anilist.co** account, used through MyAniList for iOS. This importer requests the full ANIME `MediaListCollection`, including custom lists and hidden-from-status-list entries. It validates the AniList owner and every media/list-entry ID, deduplicates entries repeated across groups, and requests both the account's native score and a `POINT_10_DECIMAL` score (0–10, one decimal). It does not create watch events from progress counts, schedule itself, or write to AniList. [AniList's list API documentation](https://docs.anilist.co/guide/graphql/queries/media-list) describes the collection and its 11,000-entry limit.

## Safe catalog behavior

- Existing stable AniList media-ID mappings are used. New standalone TV/OVA/ONA/special titles with **no anime relations** receive a show and a season; standalone anime films receive movie titles. Title strings are display text only, never a key.
- Entries with anime relations, conflicting mappings, unknown formats, or missing display titles are stored raw and sent to `marquee_mapping_review`. A verified manual mapping to an anime season, show, or film is honored on replay. Linked seasons are not grouped from title similarity.
- Status and rating rows are insert-only seeds. An existing manual, Trakt, or AniList record is never overwritten. `REPEATING` seeds `watching`, `PAUSED` seeds `on_hold`; a score of zero or null is unrated. Each source list entry and its raw score response remain in `marquee_ingest_raw` for later replay.
- A successful run advances the per-user checkpoint after all raw, catalog, review and seed writes in one transaction. An error rolls back those writes, records a failed run and leaves the last success checkpoint unchanged. Replaying a corrected mapping can fill previously unresolved seeds without another schema change.

## Operator sequence

The public-list first import and replay completed on 2026-09-23 for `Daveywavey9` after the migration was applied. All 50 entries now have stable mappings; 50 statuses and 33 ratings were seeded. This is an archival replay guide, not a pending first-import checklist. It does not create dated episode history.

1. For another environment, have the applying operator review and apply the forward migration `supabase/migrations/20260923183118_marquee_anilist_user_state_source.sql` to project `eiskobjlvxzwvucgpenk` after a GameDeck baseline check. Run `supabase/verification/05_anilist_user_state_source.sql` and the existing role/integrity checks. For this project, the migration is already applied; do not apply it twice.
2. Provide the **AniList username or profile URL** (public, no secret). For a complete list including private entries, supply an AniList OAuth access token through a secure operator environment as `ANILIST_ACCESS_TOKEN`. If Dave confirms there are no private entries, `--accept-public-list` allows a public request. A username alone cannot prove private entries are absent.
3. Run a read-only dry run, review count and related items, and verify the account identity. Then import with a session-pooler/direct `MARQUEE_DATABASE_URL` and the existing Marquee `auth.users` UUID. Never place a token, database URL or real list payload in Git, fixture files or chat.

```sh
python scripts/anilist-import/anilist_import.py \
  --username ACCOUNT_NAME --user-id EXISTING_AUTH_UUID --dry-run
# For a confirmed public-only list, append --accept-public-list.
python scripts/anilist-import/anilist_import.py \
  --username ACCOUNT_NAME --user-id EXISTING_AUTH_UUID
```

The CLI requires `ANILIST_ACCESS_TOKEN` for live source fetches unless `--accept-public-list` is explicit; both commands accept `--fixture fixtures/anilist/list.json` for offline validation. Install the pinned `psycopg[binary]==3.3.6` from `scripts/trakt-sync/requirements.txt` before any database write. The script holds a per-user session advisory lock. After a real run, report fetched, inserted, skipped and unresolved counts; inspect the review queue, then replay after verified manual mappings. Do not retry failures blindly or treat a successful run with unresolved entries as a complete catalog.
