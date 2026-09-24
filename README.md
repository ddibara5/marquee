# Marquee ingestion foundation

Marquee is an iPhone-first TV, movie, and anime tracker. The ingestion and identity foundation lives alongside the first private Marquee web app in [`web/`](web/). Recommendations remain deferred.

[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) is the sole canonical project context, copied from the ChatGPT Project attachment. Dave's later instructions can override it. The [scope summary](docs/SCOPE.md), [schema contract](docs/INGESTION_PLAN.md), and [source ownership](docs/SOURCE_OF_TRUTH.md) are implementation documents derived from that context.

The migrations under `supabase/migrations/` were applied to the shared GameDeck Supabase project `eiskobjlvxzwvucgpenk` on 2026-09-23. Read [RUNBOOK.md](docs/RUNBOOK.md) and the [verification report](docs/MIGRATION_VERIFICATION_2026-09-23.md) before subsequent changes. No source credentials belong in this repository.

Status on 2026-09-24: The first private web app is live. The earlier import history and current ingestion state are documented in [the ingestion plan](docs/INGESTION_PLAN.md); recommendations remain deferred.

## Web app

Run `cd web && npm ci && npm test && npm run build` for local validation, or `npm run dev` for development. Vercel's root directory is `web` and framework is Vite. Commit routine UI changes directly to `main`; Vercel deploys them to the stable [production URL](https://marquee-dave-0d82.vercel.app). Check the resulting deployment and revert a bad commit if needed. Create a branch preview only when explicitly requested or separate review is warranted. The client queries Marquee tables directly with a publishable Supabase key and row-level security. Ingestion changes appear on reload without a Vercel redeploy. Vercel needs no service-role credentials. The app uses the existing GameDeck owner's Supabase Auth identity; password sign-in works on the stable URL. Email links require that URL in Supabase Auth's redirect allowlist.

The Library uses canonical episode completion coverage, counting each episode once with multiple source observations. The current first-pass navigation is Library, Activity and Insights; Watchlist is preserved in the database but does not have a visible first-pass page. Activity includes dated Trakt and manual watches and eligible promptly observed Crunchyroll source-reported dates, with a source chip filter. Undated anime evidence is labeled separately on detail pages. One Piece and Fairy Tail are excluded from personal views. Manual check-ins write the current date; imported evidence is retained. Status and rating edits use `manual_locked`. Settings offers a device-local Signal red (default) or Electric blue accent. The current catalog has no poster or streaming-provider fields, so title cards use typographic covers and provider availability is deferred until metadata exists.

Progress denominators currently reflect canonical episodes present in the catalog. Many Trakt seasons contain only ingested watched episodes, so the app labels the denominator "cataloged" rather than claiming it is the full season total. A complete episode catalog or authenticated verified totals is needed for true season percentage on those titles.
