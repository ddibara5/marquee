# Trakt n8n importer

Workflow: [Marquee | Trakt six-feed importer](https://ddibara.app.n8n.cloud/workflow/FcKQLqujv4rBrWCT).

The n8n OAuth2 credential uses its own Trakt app. Keep the separate GitHub OAuth refresh chain out of n8n. The workflow fetches the complete movie and episode history, movie and show ratings, and movie and show watchlists with paginated authenticated requests. It checks each page number and total count before passing the snapshot to `public.marquee_trakt_apply_snapshot` through the Supabase service credential. Success is recorded by the RPC in `marquee_sync_runs` and `marquee_sync_state`; failures record a sanitized run without source payloads or tokens. n8n execution data saving is disabled.

The Marquee-only RPC in `supabase/migrations/20260924210000_marquee_trakt_n8n_rpc.sql` holds the same advisory lock as the Python importer. One transaction stages raw provenance and updates stable mappings, dated watch history, ratings, the watchlist and checkpoint. It creates only vetted non-anime shows; unapproved shows and mapping conflicts enter review. Manual rating and watchlist locks are preserved. Trakt watchlist removals are reconciled only when both complete watchlist feeds have no unresolved identities. Replays reuse source history IDs and do not add watches.

Switching schedules requires an authenticated manual n8n replay of all six feeds, comparison with the Python importer and GameDeck baselines, and disabling the GitHub daily schedule. Keep manual GitHub dispatch for recovery if possible. The n8n schedule is 11:17 UTC after verification; do not run both schedules. Check the next scheduled execution by its terminal `marquee_sync_runs` row and confirm `last_success_at` advances.
