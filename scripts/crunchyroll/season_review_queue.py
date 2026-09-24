#!/usr/bin/env python3
"""Prepare private Crunchyroll season review evidence; no mappings or watches."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
import re
import sys
from uuid import UUID

from catalog_overlap_probe import normalized_title, season_title_indexes
from staged_review import ReviewError, analyze, relation_edges, source_snapshot


def generic_season_label(title):
    return bool(re.fullmatch(r"(?:season|series)\s+[0-9]+", title))


def prepare(records, seasons):
    """Build review candidates keyed only by stable source season ID."""
    names = defaultdict(lambda: {"show": set(), "season": set(), "original": set(),
                                "series": set()})
    for item in records:
        panel = item.get("panel")
        metadata = panel.get("episode_metadata") if isinstance(panel, dict) else None
        if not isinstance(metadata, dict):
            continue
        season_id, series_id = metadata.get("season_id"), metadata.get("series_id")
        if not all(isinstance(x, str) and x for x in (season_id, series_id)):
            raise ReviewError("Source season identity is incomplete")
        source = names[season_id]
        source["series"].add(series_id)
        for kind, key in (("show", "series_title"), ("season", "season_title")):
            title = metadata.get(key)
            if isinstance(title, str) and title.strip():
                source[kind].add(normalized_title(title))
                if kind == "season":
                    source["original"].add(title.strip())
    if any(len(n["series"]) != 1 for n in names.values()):
        raise ReviewError("Source season ID belongs to multiple series")
    catalog = [(a, b, c, d or []) for a, b, c, d, _, _ in seasons]
    by_season, by_show = season_title_indexes(catalog)
    media_by_target = {target: media for target, _, _, _, media, _ in seasons}
    relations = relation_edges(seasons)
    result = {}
    counts = Counter()
    for season_id, name in names.items():
        specific_names = {t for t in name["season"] if t and not generic_season_label(t)}
        season_names = specific_names or name["season"]
        season_matches = set().union(*(by_season[t] for t in season_names if t))
        show_matches = set().union(*(by_show[t] for t in name["show"] if t))
        if season_names and not specific_names:
            # A generic number can narrow a named show, never identify another show.
            matches, conflict = season_matches & show_matches, False
        else:
            conflict = bool(season_matches and show_matches and not (season_matches & show_matches))
            matches = (season_matches | show_matches if conflict else
                       season_matches & show_matches if season_matches & show_matches else
                       season_matches | show_matches)
        category = ("conflicting" if conflict else "one" if len(matches) == 1
                    else "multiple" if matches else "none")
        counts[category] += 1
        candidates = []
        for target in sorted(matches):
            evidence = []
            if target in season_matches:
                evidence.append("season_title")
            if target in show_matches:
                evidence.append("series_title")
            candidates.append({"canonical_season_id": target,
                               "anilist_media_id": media_by_target[target],
                               "title_evidence": evidence,
                               "relation_to_another_candidate": any(
                                   frozenset((target, other)) in relations for other in matches if other != target),
                               "review_only": True})
        reason = {"one": "One title candidate; verify series, season, version and episode identity",
                  "multiple": "Multiple AniList title candidates; verify source identities and relations",
                  "conflicting": "Series and season title evidence conflict; manual review required",
                  "none": "No AniList title candidate; manual source identity review required"}[category]
        original = min(name["original"]) if name["original"] else None
        result[season_id] = {"candidates": candidates, "reason": reason,
                             "source_title": original}
    return result, dict(counts)


def apply_review(conn, user_id, rows, expected_ids):
    """Update open season review evidence atomically, never resolve a mapping."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtext(%s))", ("marquee:crunchyroll:" + user_id,))
            cur.execute("""select watermark->>'complete_event_count' from public.marquee_sync_state
                where source='crunchyroll' and scope_key=%s and last_success_run_id is not null""", (user_id,))
            checkpoint = cur.fetchone()
            if not checkpoint or checkpoint[0] != str(len(expected_ids)):
                raise ReviewError("Staged checkpoint changed; regenerate candidate evidence")
            cur.execute("""select dedupe_key from public.marquee_ingest_raw
                where source='crunchyroll' and source_entity_type='history_event' and scope_key=%s""", (user_id,))
            if {row[0] for row in cur.fetchall()} != expected_ids:
                raise ReviewError("Staged event IDs changed; regenerate candidate evidence")
            cur.execute("select count(*) from public.marquee_source_mappings where source='crunchyroll'")
            if cur.fetchone()[0]:
                raise ReviewError("Approved Crunchyroll mappings exist; review queue needs reconciliation")
            cur.execute("""select source_id from public.marquee_mapping_review
                where source='crunchyroll' and source_entity_type='season' and status='open'
                for update""")
            if {row[0] for row in cur.fetchall()} != set(rows):
                raise ReviewError("Open source season reviews differ from the staged snapshot")
            for source_id, entry in rows.items():
                cur.execute("""update public.marquee_mapping_review
                    set candidates=%s::jsonb,reason=%s,source_title=%s
                    where source='crunchyroll' and source_entity_type='season'
                    and source_id=%s and status='open'""",
                    (json.dumps(entry["candidates"]), entry["reason"], entry["source_title"], source_id))
                if cur.rowcount != 1:
                    raise ReviewError("A source season review could not be updated")
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--apply-review", action="store_true",
                        help="Populate private review evidence; no mappings or watches")
    args = parser.parse_args(argv)
    try:
        scope = str(UUID(args.user_id))
        database_url = os.environ.get("MARQUEE_DATABASE_URL")
        records, seasons, mappings, trakt = source_snapshot(database_url, scope)
        validation = analyze(records, seasons, mappings, trakt)
        if validation["approved_crunchyroll_episode_mappings"]:
            raise ReviewError("Approved episode mappings exist; regenerate the review plan")
        rows, counts = prepare(records, seasons)
        if len(rows) != validation["source_seasons"]:
            raise ReviewError("Candidate season coverage does not reconcile")
        output = {"source_seasons": len(rows), "title_evidence": counts,
                  "candidates_for_review": sum(len(row["candidates"]) for row in rows.values()),
                  "review_only": True, "mappings_created": 0, "canonical_watches_created": 0}
        if args.apply_review:
            import psycopg
            with psycopg.connect(database_url, connect_timeout=15) as conn:
                output["review_rows_updated"] = apply_review(
                    conn, scope, rows, {item["id"] for item in records})
        print(json.dumps(output, sort_keys=True))
        return 0
    except (ReviewError, ValueError):
        print("Crunchyroll season review preparation failed; no private records printed", file=sys.stderr)
        return 1
    except Exception:
        print("Crunchyroll season review preparation failed; check connection, no private records printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
