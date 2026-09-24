#!/usr/bin/env python3
"""Read-only staged identity review. Emit aggregates, never private records."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
import sys
from uuid import UUID

from catalog_overlap_probe import normalized_title, season_title_indexes


class ReviewError(RuntimeError):
    pass


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        raise ReviewError("Invalid source timestamp") from None


def source_snapshot(database_url, user_id):
    """Read one consistent snapshot; never echo driver exceptions or connection data."""
    if not database_url:
        raise ReviewError("Database credential is missing")
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("set transaction read only")
                cur.execute("""select payload from public.marquee_ingest_raw
                    where source='crunchyroll' and source_entity_type='history_event'
                    and scope_key=%s order by dedupe_key""", (user_id,))
                records = [row[0] for row in cur]
                cur.execute("""select s.id::text,t.display_title,s.display_title,
                           array_remove(array[r.payload #>> '{media,title,romaji}',
                                              r.payload #>> '{media,title,english}',
                                              r.payload #>> '{media,title,native}'],null),
                           m.source_id,r.payload #> '{media,relations,edges}'
                    from public.marquee_source_mappings m
                    join public.marquee_seasons s on s.id=m.season_id
                    join public.marquee_titles t on t.id=s.show_title_id
                    left join public.marquee_ingest_raw r on r.source='anilist'
                        and r.source_entity_type='media_list' and r.payload->>'mediaId'=m.source_id
                    where m.source='anilist' and m.canonical_entity_type='season'""")
                seasons = cur.fetchall()
                cur.execute("""select source_id,episode_id::text
                    from public.marquee_source_mappings
                    where source='crunchyroll' and canonical_entity_type='episode'""")
                mappings = dict(cur.fetchall())
                cur.execute("""select distinct episode_id::text
                    from public.marquee_watch_history
                    where user_id=%s and source='trakt' and episode_id is not null""", (user_id,))
                trakt_episodes = {row[0] for row in cur}
                cur.execute("""select count(*)
                    from public.marquee_watch_history
                    where user_id=%s and source='trakt' and episode_id is not null""", (user_id,))
                trakt_watch_count = cur.fetchone()[0]
                cur.execute("""select watermark->>'complete_event_count'
                    from public.marquee_sync_state
                    where source='crunchyroll' and scope_key=%s and last_success_run_id is not null""", (user_id,))
                state = cur.fetchone()
        if not state or not state[0] or int(state[0]) != len(records) or len(records) < 7933:
            raise ReviewError("Staged coverage and checkpoint disagree")
        return records, seasons, mappings, (trakt_episodes, trakt_watch_count)
    except ReviewError:
        raise
    except Exception:
        raise ReviewError("Read-only staged review could not load a consistent snapshot") from None


def relation_edges(seasons):
    """Mapped AniList relation pairs are candidate context, never automatic mappings."""
    target_by_media = {media_id: target for target, _, _, _, media_id, _ in seasons}
    edges = set()
    for target, _, _, _, _, related in seasons:
        if not isinstance(related, list):
            continue
        for edge in related:
            if not isinstance(edge, dict) or not isinstance(edge.get("node"), dict):
                continue
            other = target_by_media.get(str(edge["node"].get("id")))
            if other and other != target:
                edges.add(frozenset((target, other)))
    return edges


def candidates(names, by_season, by_show):
    season_matches = set().union(*(by_season[n] for n in names["season"] if n))
    show_matches = set().union(*(by_show[n] for n in names["show"] if n))
    if season_matches and show_matches and not (season_matches & show_matches):
        return "conflicting", season_matches | show_matches
    matches = season_matches & show_matches if season_matches & show_matches else season_matches | show_matches
    return ("one" if len(matches) == 1 else "multiple" if matches else "none"), matches


def analyze(records, seasons, mappings=(), trakt=()):
    if len(records) < 1:
        raise ReviewError("No raw records in reviewed scope")
    event_ids = set()
    panel_identity, version_owner = {}, {}
    groups = defaultdict(lambda: {"panels": set(), "season_ids": set(),
                                  "series_ids": set(), "numbers": set(), "versions": None,
                                  "events": []})
    season_names = defaultdict(lambda: {"season": set(), "show": set()})
    counts = Counter()
    source_timestamps = Counter()
    missing_parent_counts = Counter()
    known_series = set()
    for event in records:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"]:
            raise ReviewError("Source event ID is missing")
        if event["id"] in event_ids:
            raise ReviewError("Duplicate source event ID")
        event_ids.add(event["id"])
        at = timestamp(event.get("date_played"))
        source_timestamps[at] += 1  # Contract check and collision diagnostic only.
        panel = event.get("panel")
        metadata = panel.get("episode_metadata") if isinstance(panel, dict) else None
        if not isinstance(metadata, dict) or not isinstance(panel.get("id"), str) or not panel["id"]:
            counts["without_panel"] += 1
            missing_parent_counts[event.get("parent_id")] += 1
            continue
        panel_id = panel["id"]
        series, season, identifier = (metadata.get(k) for k in ("series_id", "season_id", "identifier"))
        versions = metadata.get("versions")
        if not all(isinstance(v, str) and v for v in (series, season, identifier)) or not isinstance(versions, list):
            raise ReviewError("Episode source identity changed shape")
        known_series.add(series)
        counts["parent_matches_series" if event.get("parent_id") == series else "parent_series_mismatch"] += 1
        guids = [v.get("guid") if isinstance(v, dict) else None for v in versions]
        if not guids or any(not isinstance(v, str) or not v for v in guids) or len(guids) != len(set(guids)) or panel_id not in guids:
            raise ReviewError("Episode version GUID list is incomplete or inconsistent")
        for guid in guids:
            if guid in version_owner and version_owner[guid] != identifier:
                raise ReviewError("Version GUID belongs to multiple episodes")
            version_owner[guid] = identifier
        number = metadata.get("episode_number")
        number = int(number) if (type(number) is int or isinstance(number, str) and number.isdecimal()) and int(number) > 0 else None
        prior = panel_identity.get(panel_id)
        identity = (identifier, series, season, number)
        if prior and prior != identity:
            raise ReviewError("Episode panel identity changed between observations")
        panel_identity[panel_id] = identity
        group = groups[identifier]
        guid_set = frozenset(guids)
        if group["versions"] is not None and group["versions"] != guid_set:
            raise ReviewError("Episode identifier has conflicting version sets")
        group["versions"] = guid_set
        group["panels"].add(panel_id)
        group["season_ids"].add(season)
        group["series_ids"].add(series)
        group["numbers"].add(number)
        group["events"].append((panel_id, event.get("fully_watched")))
        season_names[season]["show"].add(normalized_title(metadata.get("series_title")))
        season_names[season]["season"].add(normalized_title(metadata.get("season_title")))
        counts["panel_observations"] += 1
    by_season, by_show = season_title_indexes([(a, b, c, d or []) for a, b, c, d, _, _ in seasons])
    season_candidates = {season: candidates(names, by_season, by_show)
                         for season, names in season_names.items()}
    season_categories = Counter(kind for kind, _ in season_candidates.values())
    version_categories = Counter()
    relation_pairs = relation_edges(seasons)
    related_ambiguous = 0
    approved_targets = dict(mappings)
    trakt_episodes, trakt_watch_count = trakt if trakt else (set(), 0)
    overlap = Counter()
    for group in groups.values():
        if len(group["series_ids"]) != 1 or len(group["numbers"]) != 1:
            raise ReviewError("Source version group crosses series or episode number")
        if None in group["numbers"]:
            counts["groups_without_episode_number"] += 1
        if len(group["panels"]) > 1:
            counts["multi_panel_version_groups"] += 1
        categories = [season_candidates[s] for s in group["season_ids"]]
        kinds = {kind for kind, _ in categories}
        targets = set().union(*(matches for _, matches in categories))
        if "conflicting" in kinds:
            label = "conflicting_title_evidence"
        elif len(targets) == 1 and kinds == {"one"}:
            label = "consistent_one_title_candidate"
        elif len(targets) == 1:
            label = "partial_one_title_candidate"
        elif len(targets) > 1:
            label = "multiple_title_candidates"
        else:
            label = "no_title_candidate"
        version_categories[label] += 1
        if len(targets) > 1 and any(edge <= targets for edge in relation_pairs):
            related_ambiguous += 1
        if any(fully is not True and fully is not False for _, fully in group["events"]):
            raise ReviewError("Playback completion status is invalid")
        counts["completed_source_episode_groups" if any(fully for _, fully in group["events"])
               else "partial_only_source_episode_groups"] += 1
        mapped = {approved_targets[p] for p in group["panels"] if p in approved_targets}
        if len(mapped) > 1:
            raise ReviewError("Source versions map to different canonical episodes")
        if len(mapped) == 1:
            overlap["approved_crunchyroll_episode_groups"] += 1
            if next(iter(mapped)) in trakt_episodes:
                overlap["same_canonical_episode_has_trakt_watches"] += 1
    if counts["panel_observations"] + counts["without_panel"] != len(records):
        raise ReviewError("History coverage does not reconcile")
    return {"raw_events": len(records), "with_panel": counts["panel_observations"],
            "without_panel": counts["without_panel"],
            "source_seasons": len(season_names), "source_panels": len(panel_identity),
            "source_episode_version_groups": len(groups),
            "multi_panel_version_groups": counts["multi_panel_version_groups"],
            "completed_source_episode_groups": counts["completed_source_episode_groups"],
            "partial_only_source_episode_groups": counts["partial_only_source_episode_groups"],
            "groups_without_episode_number": counts["groups_without_episode_number"],
            "distinct_source_timestamps": len(source_timestamps),
            "events_at_timestamps_shared_by_100_plus": sum(
                n for n in source_timestamps.values() if n >= 100),
            "parent_matches_series": counts["parent_matches_series"],
            "parent_series_mismatch": counts["parent_series_mismatch"],
            "missing_panel_parents_seen_as_series": len(missing_parent_counts.keys() & known_series),
            "missing_panel_events_with_known_series": sum(
                n for parent, n in missing_parent_counts.items() if parent in known_series),
            "missing_panel_parents_not_seen_as_series": len(missing_parent_counts.keys() - known_series),
            "season_title_evidence": dict(season_categories),
            "version_group_title_evidence": dict(version_categories),
            "ambiguous_groups_with_anilist_relation_edge": related_ambiguous,
            "approved_crunchyroll_episode_mappings": len(approved_targets),
            "trakt_episode_watches": trakt_watch_count, "identity_overlap": dict(overlap),
            "note": "Crunchyroll playback dates are untrusted. Same timestamps do not prove duplicate watches or Trakt overlap. AniList candidates require review. No mapping or watch was written."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args(argv)
    try:
        user_id = str(UUID(args.user_id))
        snapshot = source_snapshot(os.environ.get("MARQUEE_DATABASE_URL"), user_id)
        print(json.dumps(analyze(*snapshot), sort_keys=True))
        return 0
    except (ReviewError, ValueError):
        print("Read-only identity review failed; no private source records printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
