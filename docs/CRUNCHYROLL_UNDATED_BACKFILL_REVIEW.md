# Crunchyroll historical-watch review plan

Status: proposal only. No schema migration, source mapping, canonical watch, or scheduler is authorized by this document.

## What the staged data establishes

| Evidence | Count | Meaning |
| --- | ---: | --- |
| Raw history observations | 7,933 | Private source records preserved by event ID. |
| Observations with episode panels | 5,979 | These carry source episode and version identity. |
| Distinct source episode identifiers | 3,130 | Version GUID sets are disjoint; this is not yet a count of canonical AniList episodes. |
| Source episode identifiers with any complete playback | 3,009 | Candidate historical completions, subject to identity review. |
| Source episode identifiers with partial playback only | 121 | Not completed watches. |
| Episode identifier groups with no usable episode number | 8 | Require individual identity review. |
| Observations without episode panels | 1,954 | Cannot establish an episode; 1,953 have a parent ID seen as a series elsewhere. |

Crunchyroll `date_played` is untrusted. There are 1,631 distinct source timestamps across 7,933 observations, and 6,156 observations use five identical timestamp values. Different timestamps cannot establish separate rewatch occasions; identical timestamps cannot establish duplicate observations. The source values remain private raw evidence, never a canonical `watched_at`.

## Mapping and overlap order

1. The **existing 222 open season reviews** now contain 307 AniList title candidates (135 seasons have one, 11 multiple, 19 conflicting, and 57 none). [One-time run 35944472562](https://github.com/ddibara5/marquee/actions/runs/35944472562) updated only those private review rows, then its temporary trigger was removed. All 222 source titles and 307 candidate entries were verified in the database; zero mappings and watches were created. Among the 135 single-title candidate seasons, 53 have an AniList start year within one year of the observed Crunchyroll episode-air-year span and 82 do not. This is a prioritization clue, not proof of identity or a reason to automatically reject a dub/version.
2. Review stable Crunchyroll series and season IDs against approved AniList media IDs and franchise relations. Confirm numbering, seasons, language versions, and the nine parent/episode-series disagreements. A title match by itself never approves a mapping. The read-only `parent_catalog_probe.py` can check the seven missing-panel parent IDs against the Crunchyroll series catalog without emitting titles or IDs. Even a successful catalog lookup does not identify an episode.
3. For each source episode identifier, validate that every observed version GUID belongs to one reviewed source episode and one canonical episode. Require usable episode numbering or explicit manual corroboration. Lock only verified source-ID mappings. Do not infer a completed episode from a parent series ID or partial-only playback.
4. Compare approved canonical episode IDs with Trakt. Keep Trakt's independently recorded date on its own watch. Do not use the Crunchyroll timestamp to decide that the two services saw the same viewing occasion. AniList list status and rating provide no episode date.

## Proposed undated storage contract

The applied `marquee_watch_history.watched_at` is `NOT NULL`. Do not put a placeholder date there or weaken its dated Trakt contract. Propose two new `marquee_` tables in a separately reviewed migration:

- `marquee_undated_episode_completions`: one row per `(user_id, episode_id)`, foreign keys to `auth.users` and `marquee_episodes`, creation/update timestamps for database bookkeeping only. No playback date and no fabricated event count. Authenticated users may read only their own rows; service role performs reviewed writes.
- `marquee_undated_episode_evidence`: one row per completed raw Crunchyroll event, keyed by the existing `marquee_ingest_raw.id`, with `(user_id, episode_id)` referencing the completion and a stable source episode identifier. This retains every source event without treating event count as distinct watches. Service role only. A raw event cannot point to two canonical episodes.

Progress and “watched” displays use the union of dated and undated episode IDs per user, counting each canonical episode once. Dated Trakt viewings retain their own event records and dates. A repeated import must make no extra completion or evidence rows. Source remapping requires an explicit review and replay transaction; never silently retarget evidence. If a separately corroborated date appears later, add or correct a dated event through a reviewed path; do not promote the raw Crunchyroll timestamp.

## Backfill gates

- Present the approved series/season/episode mapping coverage, unresolved identities, and the canonical episode count after cross-version and cross-source collapse.
- Review the migration, owner-scoped access policies, replay/rollback behavior, and duplicate prevention before any live schema or data write.
- Test fabricated fixtures for repeat imports, partial-only observations, conflicting version mappings, missing panels, and a dated Trakt watch of the same canonical episode.
- Verify GameDeck `game_ranks=53` and `rank_comparisons=154` before and after any approved migration or backfill. Keep n8n inactive until the backfill is separately approved and verified.
