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
2. Review stable Crunchyroll series and season IDs against approved AniList media IDs and franchise relations. Confirm numbering, seasons, language versions, and the nine parent/episode-series disagreements. A title match by itself never approves a mapping. [Read-only parent catalog run 35944949861](https://github.com/ddibara5/marquee/actions/runs/35944949861) verified all seven missing-panel parent IDs as Crunchyroll series IDs, including the previously unseen seventh; it identified no missing episode and wrote nothing.
3. [Read-only AniList count and external-link checks](https://github.com/ddibara5/marquee/actions/runs/35945631059) compared the 135 single-title source seasons with the 30 AniList media they point to. In 85 seasons the highest observed Crunchyroll episode number fits AniList's published total; 49 exceed it and one has no usable number. Exactly 24 candidate seasons have an AniList external Crunchyroll URL containing the **same stable Crunchyroll series ID**, covering 10 source series and 12 AniList media. Thirteen of those 24 also have a compatible year and episode-number range. Exact series ID corroborates the parent series, not which source season/version corresponds to an AniList season, and never proves an episode or watch date. Treat the other 111 single-title candidates as title evidence only.
   [The stricter read-only proposal run 35946684910](https://github.com/ddibara5/marquee/actions/runs/35946684910) checked all title candidates for each source series against their canonical show targets and checked parent/episode-series disagreements. Nine of the ten exact-linked series have one consistent show target; the tenth has a candidate for a different show and stays in review. None of the nine is implicated in the parent mismatches. The nine links are proposed **series-to-show identities only**. No season, episode, completion, or date follows from them; the one conflicting series and all season reviews remain unresolved. The temporary workflow was removed after the run.
4. For each source episode identifier, validate that every observed version GUID belongs to one reviewed source episode and one canonical episode. Require usable episode numbering or explicit manual corroboration. Lock only verified source-ID mappings. Do not infer a completed episode from a parent series ID or partial-only playback.
5. Compare approved canonical episode IDs with Trakt. Keep Trakt's independently recorded date on its own watch. Do not use the Crunchyroll timestamp to decide that the two services saw the same viewing occasion. AniList list status and rating provide no episode date.

## Proposed undated storage contract

The applied `marquee_watch_history.watched_at` is `NOT NULL`. Do not put a placeholder date there or weaken its dated Trakt contract. Propose two new `marquee_` tables in a separately reviewed migration:

- `marquee_undated_episode_completions`: one row per `(user_id, episode_id)`, foreign keys to `auth.users` and `marquee_episodes`, creation/update timestamps for database bookkeeping only. No playback date and no fabricated event count. Authenticated users may read only their own rows; service role performs reviewed writes.
- `marquee_undated_episode_evidence`: one row per completed raw Crunchyroll event, keyed by the existing `marquee_ingest_raw.id`, with `(user_id, episode_id)` referencing the completion and a stable source episode identifier. This retains every source event without treating event count as distinct watches. Service role only. A raw event cannot point to two canonical episodes.

Progress and “watched” displays use the union of dated and undated episode IDs per user, counting each canonical episode once. Dated Trakt viewings retain their own event records and dates. A repeated import must make no extra completion or evidence rows. Source remapping requires an explicit review and replay transaction; never silently retarget evidence. If a separately corroborated date appears later, add or correct a dated event through a reviewed path; do not promote the raw Crunchyroll timestamp.

## Backfill gates

- Review the nine exact-ID series-to-show proposals before inserting mappings. Recompute the source-ID links and all candidate show targets from a fresh complete staged snapshot. In one guarded transaction, require the same raw-event ID set and checkpoint, the same open season-review evidence, existing canonical show FKs, and no conflicting or manually locked source mapping. Insert only `(source='crunchyroll', source_entity_type='series', canonical_entity_type='show')` mappings by stable series ID; repeat application must create zero new rows. Keep the tenth conflicting series in review. This is a distinct decision from approving any season or episode identity.
- Present the approved series/season/episode mapping coverage, unresolved identities, and the canonical episode count after cross-version and cross-source collapse.
- Review the migration, owner-scoped access policies, replay/rollback behavior, and duplicate prevention before any live schema or data write.
- Test fabricated fixtures for repeat imports, partial-only observations, conflicting version mappings, missing panels, and a dated Trakt watch of the same canonical episode.
- Verify GameDeck `game_ranks=53` and `rank_comparisons=154` before and after any approved migration or backfill. Keep n8n inactive until the backfill is separately approved and verified.
