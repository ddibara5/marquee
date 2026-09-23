# Trakt importer

The repository is canonical for this importer. `trakt_sync.py` is a Python 3.11+ command-line process, separate from n8n. It reads the six Trakt sync feeds (movie and episode history; movie and show ratings; movie and show watchlists), preserves raw records and source IDs, and writes Marquee catalog and user state. It never uses titles as durable identity keys.

## Run requirements

- A Trakt **client ID and user OAuth access token** in `TRAKT_CLIENT_ID` and `TRAKT_ACCESS_TOKEN`. A client ID alone does not authorize private sync feeds. Tokens expire; the operator must refresh and store replacement tokens securely. Never put a token in arguments, fixtures, logs, chat, or Git.
- `MARQUEE_DATABASE_URL`: a secure direct Postgres or session-pooler connection to the existing shared Supabase project with permission to write `marquee_*` tables. Transaction pooling cannot hold the script's session advisory lock. The target Supabase user ID must already exist in `auth.users`.
- Outbound access to `api.trakt.tv` and the database from the runner. A Trakt bridge is optional: it would need to provide the same six feed shapes plus complete pagination; its callable interface has not been supplied, so this version calls Trakt directly.
- A reviewed JSON array of Trakt show IDs that are **non-anime**, passed as `--approved-shows`. Existing stable mappings to a non-anime show are also eligible. New unapproved shows go to `marquee_mapping_review` with their raw records. The supplied file in `fixtures/` contains fabricated IDs for tests only.

Install `python -m pip install -r scripts/trakt-sync/requirements.txt` in a private runtime. Run offline validation without credentials:

```sh
python scripts/trakt-sync/trakt_sync.py --user-id 00000000-0000-4000-8000-000000000001 --fixture-dir fixtures/trakt --approved-shows fixtures/trakt/approved_non_anime_shows.json --dry-run
python -m unittest discover -s tests -p 'test_trakt*.py'
```

For a real run, provide the three environment variables securely and run:

```sh
python scripts/trakt-sync/trakt_sync.py --user-id YOUR_EXISTING_AUTH_UUID --approved-shows PATH_TO_REVIEWED_SHOW_IDS.json --dry-run
python scripts/trakt-sync/trakt_sync.py --user-id YOUR_EXISTING_AUTH_UUID --approved-shows PATH_TO_REVIEWED_SHOW_IDS.json
```

No live Trakt or Supabase import has been run or approved by this README. Review source counts, mapping policy and overlapping anime observations before the first write. Do not pass real credentials through chat.

## Replay and operations

The importer fetches complete snapshots and checks every page's count and identity before writing. It uses a per-user Postgres advisory lock, records a sync run, then writes raw records, mappings, review entries, state and the success checkpoint in one transaction. Any failed fetch or write records a failed run and leaves the success checkpoint untouched. The watermark is an audit marker; it is never used to skip past older watches or ratings. Replaying identical records uses stable IDs and unique keys and preserves manual rows and locked mappings. A completed, fully resolved watchlist is reconciled against Trakt; a watchlist with unresolved identities leaves existing entries in place.

Movie and vetted non-anime TV observations are imported. Unapproved shows and ambiguous external mappings enter review; missing stable IDs or unexpected payload shapes fail the entire run. Episode ratings are outside the current Marquee rating schema. Overlap with Crunchyroll anime is deferred until the documented cross-source rule is verified on real timestamps.

Ongoing scheduling belongs to a durable private runner with secure OAuth token rotation, or an authenticated endpoint that n8n can trigger. This repository holds the code and contract; n8n does not execute this Python file on n8n Cloud.
