# Source of truth

| Domain | Authority | Other sources and precedence |
| --- | --- | --- |
| Non-anime TV and movie watch history | Trakt | Store every observation in raw ingestion. Manual corrections outrank imports. |
| Anime episode completions | AniList manual list and Crunchyroll | Verified episodes count once across sources. Trakt retains dated watches; raw Crunchyroll observations retain their unverified timestamps. |
| Anime identity, season entries, schedules and explicit relations | AniList | Stable AniList ID maps to a season. Franchise rules require an approved relation allowlist; unusual graphs go to review. |
| Initial anime status and score | Dave's anilist.co account via MyAniList on iOS | Seed using stable AniList media and list-entry IDs. Never replace existing status or rating. |
| Artwork, metadata and watch providers | TMDb | Deferred until PWA work. Retain available TMDb/IMDb IDs from Trakt now. |
| Marquee user edits | Manual | A manual lock wins over automatic mapping or state refresh. |

`marquee_source_mappings` owns stable external identity. `marquee_ingest_raw` owns source evidence. Canonical catalog and user tables are projections and can be rebuilt from evidence plus manual overrides. Review candidates are never promoted by title similarity alone.

Cross-source overlap rule for later adapters: an identical stable source observation always resolves to the same evidence row. For historical episode **completion**, union confirmed AniList manual progress, Crunchyroll playback and dated Trakt history by verified canonical episode ID, once per user and episode. Preserve each source observation. Crunchyroll timestamps of mixed quality do not prove a viewing occasion or a rewatch; retain them as raw evidence. Trakt keeps its independently recorded date and distinct dated viewing events. Merge two events as one viewing occasion only with independent corroboration or an explicit owner decision; source timestamps alone are insufficient. Treat verified movie completions the same way by movie identity.
