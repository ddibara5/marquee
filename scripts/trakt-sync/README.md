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

Dave approved the first live import on 2026-09-23. The [first run](https://github.com/ddibara5/marquee/actions/runs/35890598381) and [replay](https://github.com/ddibara5/marquee/actions/runs/35896718778) succeeded. Future runs remain manual. Do not pass real credentials through chat.

## Authorize Dave's dedicated Marquee app

On Dave's trusted computer, install [GitHub CLI](https://cli.github.com/) and authenticate as a repository owner with `gh auth login`. Run `gh auth status` and verify the active account can edit `ddibara5/marquee` Actions secrets. Download the latest repo or clone it locally, then run:

```sh
python3 scripts/trakt-sync/authorize.py
```

Enter the dedicated Marquee app's client ID and client secret into the local hidden prompts. Open the Trakt verification URL and enter the short code that the helper prints; approve **Marquee** under Dave's Trakt account. The helper sends the credentials and newly issued user access and refresh tokens to the four **repository Actions secrets** via `gh secret set`. It does not put secrets in shell history, code, a file, or terminal output. Do not upload screenshots of credential pages or run the existing manual importer while secrets are being replaced. If a GitHub secret write fails, leave the workflow manual and rerun device authorization rather than trying to recover a partially used token.

The resulting `TRAKT_CLIENT_ID` and `TRAKT_ACCESS_TOKEN` pair allows manual imports for the token's current lifetime. `TRAKT_CLIENT_SECRET` and `TRAKT_REFRESH_TOKEN` are stored for a future refresh runner; **this helper does not enable automatic rotation, and the current importer does not read those two secrets. Do not add a schedule yet.** Trakt refresh tokens are single-use: any future refresh must securely persist both replacement tokens before running the importer. The operator should test a read-only dry run and one replay after authorization. Leave the old Muse Trakt connection intact until the new app is verified.

## Replay and operations

The importer fetches complete snapshots and checks every page's count and identity before writing. It uses a per-user Postgres advisory lock, records a sync run, then writes raw records, mappings, review entries, state and the success checkpoint in one transaction. Any failed fetch or write records a failed run and leaves the success checkpoint untouched. The watermark is an audit marker; it is never used to skip past older watches or ratings. Replaying identical records uses stable IDs and unique keys and preserves manual rows and locked mappings. A completed, fully resolved watchlist is reconciled against Trakt; a watchlist with unresolved identities leaves existing entries in place.

Movie and vetted non-anime TV observations are imported. Unapproved shows and ambiguous external mappings enter review; missing stable IDs or unexpected payload shapes fail the entire run. Episode ratings are outside the current Marquee rating schema. Overlap with Crunchyroll anime is deferred until the documented cross-source rule is verified on real timestamps.

Ongoing scheduling belongs to a durable private runner with secure OAuth token rotation, or an authenticated endpoint that n8n can trigger. This repository holds the code and contract; n8n does not execute this Python file on n8n Cloud.
