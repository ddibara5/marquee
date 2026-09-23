# Source of truth

| Domain | Authority | Other sources and precedence |
| --- | --- | --- |
| Non-anime TV and movie watch history | Trakt | Store every observation in raw ingestion. Manual corrections outrank imports. |
| Ongoing anime episode history | Crunchyroll | Trakt overlap is kept as evidence and linked to one canonical event. |
| Anime identity, season entries, schedules and explicit relations | AniList | Stable AniList ID maps to a season. Franchise rules require an approved relation allowlist; unusual graphs go to review. |
| Initial anime status and score | MAL via Jikan | Seed once only. Never replace a newer manual, Trakt or Crunchyroll state. Score zero means unrated. |
| Artwork, metadata and watch providers | TMDb | Deferred until PWA work. Retain available TMDb/IMDb IDs from Trakt now. |
| Marquee user edits | Manual | A manual lock wins over automatic mapping or state refresh. |

`marquee_source_mappings` owns stable external identity. `marquee_ingest_raw` owns source evidence. Canonical catalog and user tables are projections and can be rebuilt from evidence plus manual overrides. Review candidates are never promoted by title similarity alone.

Cross-source overlap rule for later adapters: an identical stable source observation always resolves to the same canonical watch event. For distinct Trakt and Crunchyroll observations, compare canonical episode and source timestamps within a documented window; merge only with deterministic evidence, otherwise queue a review. Preserve both source observations. Do not collapse distinct same-day rewatches simply because they share an episode.
