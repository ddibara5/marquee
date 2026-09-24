# Crunchyroll incremental sync in n8n

The live draft workflow is **Marquee | Crunchyroll incremental history (review first)**, ID `4ydlrCseHNViR3QM`. It is inactive, and its daily 09:00 UTC trigger is disabled pending the first authenticated manual run. The checked-in JSON is a portable template with credential ID placeholders; edit credentials in n8n, never in this file. The two `2026092420*` migrations have already been applied to the shared Supabase project and are tracked in the repo.

## Finish credential setup

1. In n8n Credentials, open **Marquee Crunchyroll cookie — replace placeholder**. Set its Header Auth `Name` to `Cookie` and `Value` to `etp_rt=<current cookie value>` using n8n's credential editor. Do not paste that value into chat, code, workflow parameters, or an execution note. This credential is restricted to `www.crunchyroll.com`.
2. The HTTP Request node **Ingest Marquee verified window** uses the existing **GameDeck Supabase (service)** credential because GameDeck and Marquee share project `eiskobjlvxzwvucgpenk`. Verify that credential points to this project; no GameDeck tables are written. Its role must be `service_role` because the RPC is not callable by anon/authenticated clients. Do not copy its key into the workflow.
3. Run the manual trigger once and inspect only the aggregate RPC response. Confirm the run status, new event count, held count, completion/evidence counts, and GameDeck baseline (53 ranks / 154 comparisons). Then enable the daily trigger and activate/publish the workflow. If the credential fails, update it in n8n before retrying. Leave the schedule disabled until the manual run succeeds.

## Behavior and stop conditions

- The HTTP node asks Crunchyroll for 20 recent pages at most, with 20 events per page. The Code node checks event shape, unique event IDs, parseable source timestamps, and same-account, sequential pagination. The account check and database checkpoint prevent a different profile from being imported. The database insists that the last 40 fetched IDs already exist in the staged snapshot; if more than 360 new events arrive between runs, it rejects the entire transaction. Expand and review the window deliberately if this occurs; do not bypass the overlap test.
- The Marquee RPC ingests only manually locked source episode mappings as undated completions. It keeps all fetched source dates in private raw evidence, never creates dated watches or rewatches, excludes One Piece and Fairy Tail by panel series or parent ID, and holds unknown episodes in mapping review. Dub versions and multiple observations attach evidence to the same canonical completion. A published season total can promote an unlocked status to completed when every canonical episode is covered.
- All raw writes, evidence, status updates, run metadata and the checkpoint happen in one Marquee transaction. Any rejected window rolls them back. The function exposes only aggregate success counts or a sanitized SQLSTATE error. Workflow execution data retention is disabled for success, error and manual runs; keep it that way because upstream nodes handle the bearer token and private history.
- The 80 reviewed season totals are seeded in `marquee_verified_season_totals`. New media, changed season lengths or newly verified source mappings require a reviewed migration; unknown events are staged and held rather than guessed.

## Maintenance

Check the Marquee sync state and run counts after each change. On a failed overlap or changed source shape, inspect the source safely and adjust the importer or reviewed mapping before rerunning; the prior checkpoint remains. If Crunchyroll changes its auth endpoint or public client identifier, update the documented public client exchange and revalidate the workflow. Rotate the cookie only inside n8n. Do not run the old full-history stage job as the daily importer.
