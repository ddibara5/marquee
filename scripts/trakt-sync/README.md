# Trakt sync (planned Phase 2)

The portable importer will live here as a command-line program. It will fetch Trakt movie and non-anime TV history, ratings, and watchlist through a transport adapter; paginate and retain source IDs and raw records; resolve stable mappings or enqueue ambiguous records; upsert canonical and user state idempotently; and advance a checkpoint only after required writes succeed. Sanitized fixtures and replay tests will live in `fixtures/` and `tests/`.

Muse's existing Trakt bridge can supply the transport if its callable interface is available to the job runner. The bridge handles access to Trakt; the repository owns import and mapping logic. If the bridge is limited to an interactive Muse session, use a direct Trakt API transport with runtime credentials for the scheduled job. No credentials belong in Git.

Run the program initially in an operator environment with bridge access and secure configuration. For recurring sync, deploy the same program as a separately scheduled process on a durable runner. An n8n workflow may trigger an authenticated runner endpoint and report failures, but it does not contain or execute this repository's script. Confirm the bridge interface and durable runner before wiring live schedules; do not activate n8n during importer development.
