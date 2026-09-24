# Trakt importer

The [n8n importer](N8N.md) is the recurring runner. This document also describes the original Python importer, retained for manual recovery and comparison. Both read the same six Trakt sync feeds (movie and episode history; movie and show ratings; movie and show watchlists), preserve raw records and source IDs, and never use titles as durable identity keys.

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

### GitHub Actions setup (no local software)

Historical GitHub recovery setup: in `ddibara5/marquee` repository **Settings > Secrets and variables > Actions**, these three secrets were used. The n8n OAuth credential uses a separate Trakt app and must not share GitHub's refresh-token chain:

| Secret | Value |
| --- | --- |
| `TRAKT_MARQUEE_CLIENT_ID` | Client ID shown on Dave's dedicated Marquee Trakt developer app. |
| `TRAKT_MARQUEE_CLIENT_SECRET` | Client secret shown on that same app. |
| `MARQUEE_SECRETS_WRITE_TOKEN` | A fine-grained GitHub personal access token restricted to **only** `ddibara5/marquee`, with **repository Secrets: Read and write**; no Contents write permission. Store it only in this GitHub Actions secret, never in chat or repo files. Track its expiration. |

After the three secrets exist, Dave manually dispatches **Trakt authorize Marquee (manual)** from the GitHub Actions tab. Open the running **Display device code and wait for approval** step. It displays the Trakt activation URL and a short user code, not an OAuth token. On Trakt, sign into Dave's account, enter the code and approve **Marquee** before the job's 15-minute timeout. On success, the job writes the client ID plus both newly issued OAuth tokens as **one** `TRAKT_OAUTH_BUNDLE` repository secret. GitHub encrypts the secret; the workflow never prints its value. Confirm the job succeeded and the new secret name appears in GitHub Settings.

Authorization succeeded in [run 35919059666](https://github.com/ddibara5/marquee/actions/runs/35919059666). The import workflow now requires the Marquee bundle and matching app client ID; the legacy Muse tokens are no longer an import fallback. Trakt access tokens last seven days and refresh tokens are single-use. When the bundle is five days old, the runner requests a fresh pair and replaces the **single** GitHub Actions secret before starting the importer. Both workflows share a concurrency group, so they cannot rotate the same token simultaneously. Refresh failures stop the import. If Trakt accepts refresh but GitHub cannot save the replacements, rerun device authorization; the old refresh token has been consumed. The fine-grained GitHub token can write *any* Actions secret in this repo, so keep it restricted and rotate it under operator control.

For refresh, set the repository **Actions variable** `TRAKT_MARQUEE_REDIRECT_URI` to the **exact redirect URI configured on Dave's Marquee Trakt developer app** (for example `urn:ietf:wg:oauth:2.0:oob` only if that URI is registered on the app). Trakt's token endpoint documents this field as required. A missing value fails closed when refresh becomes due; it does not send an unverified URI or consume the refresh token. This value is not an OAuth token. A manual dry run with a newly issued bundle does not exercise refresh, so before scheduling, verify this setting and a controlled refresh using the app's actual redirect URI. Never post OAuth tokens or screenshots of the app credentials.

The manual **Trakt sync** dispatch defaults to `dry_run: true`, which fetches and validates every page without connecting to Supabase. After reviewing that result, dispatch again with `dry_run: false` for the idempotent database replay. To verify rotation without waiting five days, set the exact redirect URI variable and dispatch with `dry_run: true` and `refresh_now: true`: this consumes the current refresh token and saves a replacement pair, then validates Trakt pages without database writes. The controlled refresh [succeeded on September 23](https://github.com/ddibara5/marquee/actions/runs/35927368280), validating all six feeds after the new bundle was saved. The full Marquee-token [database replay](https://github.com/ddibara5/marquee/actions/runs/35924066473) matched prior counts with zero new history rows.

The GitHub schedule previously ran at **11:17 UTC**. It is disabled after the verified n8n replay; the workflow remains available by manual dispatch for recovery. Do not run both importers at the same time. If recovering through GitHub, keep `MARQUEE_SECRETS_WRITE_TOKEN` valid for token refresh.

### Local fallback

On Dave's trusted computer, install [GitHub CLI](https://cli.github.com/) and authenticate as a repository owner with `gh auth login`. Run `gh auth status` and verify the active account can edit `ddibara5/marquee` Actions secrets. Download the latest repo or clone it locally, then run:

```sh
python3 scripts/trakt-sync/authorize.py
```

Enter the dedicated Marquee app's client ID and client secret into the local hidden prompts. Open the Trakt verification URL and enter the short code that the helper prints; approve **Marquee** under Dave's Trakt account. The helper sends the credentials and newly issued user access and refresh tokens to the four **repository Actions secrets** via `gh secret set`. It does not put secrets in shell history, code, a file, or terminal output. Do not upload screenshots of credential pages or run the existing manual importer while secrets are being replaced. If a GitHub secret write fails, leave the workflow manual and rerun device authorization rather than trying to recover a partially used token.

The local fallback writes the legacy `TRAKT_CLIENT_ID` and `TRAKT_ACCESS_TOKEN` pair, which the current GitHub Actions import no longer reads. Use the GitHub Actions authorization path for the ongoing runner. Leave the old Muse Trakt connection intact until the new app is verified.

## Replay and operations

The importer fetches complete snapshots and checks every page's count and identity before writing. It uses a per-user Postgres advisory lock, records a sync run, then writes raw records, mappings, review entries, state and the success checkpoint in one transaction. Any failed fetch or write records a failed run and leaves the success checkpoint untouched. The watermark is an audit marker; it is never used to skip past older watches or ratings. Replaying identical records uses stable IDs and unique keys and preserves manual rows and locked mappings. A completed, fully resolved watchlist is reconciled against Trakt; a watchlist with unresolved identities leaves existing entries in place.

Movie and vetted non-anime TV observations are imported. Unapproved shows and ambiguous external mappings enter review; missing stable IDs or unexpected payload shapes fail the entire run. Episode ratings are outside the current Marquee rating schema. Overlap with Crunchyroll anime is deferred until the documented cross-source rule is verified on real timestamps.

The ongoing scheduler is n8n. It invokes the Marquee-only transaction in `supabase/migrations/20260924210000_marquee_trakt_n8n_rpc.sql`; n8n Cloud does not execute this Python file.
