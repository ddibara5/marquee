# Marquee phone UI study · 2026-09-24

Interactive mockup: [`web/public/mockups/marquee-directions.html`](../web/public/mockups/marquee-directions.html). This is a design study with illustrative counts and titles, no live Supabase calls or stored edits. It is served at `/mockups/marquee-directions.html` in a Vercel branch preview. Do not treat its sample data as a source-of-truth snapshot.

## Decisions supplied by Dave

- Activity needs its own tab; Library is separate.
- Insights is a possible third tab. Make its value visible before committing to it.
- Leave Watchlist out of this first pass; avoid pages that do not earn their place.
- Compare Continue Watching first and Full Collection first in the Library mockup.
- Explore a dark, vivid, game/movie-inspired direction, comparing blue and red accents.

## Open for review

- Which Library opening works better day to day?
- Does Insights add enough value for a tab, or should the first pass have just Library and Activity?
- Which accent feels more like Marquee? The shipped app's current gold is not assumed final.
- Does Library need a separate saved-list entry point later? It is intentionally absent here.

## Scope and data boundaries

The mockup demonstrates Library → show → season → episode, a simulated check-in, Activity with distinct Trakt/manual/recent Crunchyroll labels, and optional Insights metrics that the current data model can calculate. Watchlist, Explore, recommendations, and streaming-provider cards are omitted. Progress denominators say `cataloged`; historical undated completions contribute to progress but not monthly dated activity. Colors are one accent at a time, with dark tonal surfaces and a luminous progress trace. All data and actions are illustrative until connected in the actual app.

After feedback, record approved direction in `DESIGN.md`, implement in `web/src`, and verify authenticated flows at an iPhone viewport on a separate Vercel preview before production.
