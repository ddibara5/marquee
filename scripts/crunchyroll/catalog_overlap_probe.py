#!/usr/bin/env python3
"""Read-only Crunchyroll/AniList catalog candidate counts; never logs source records."""

from __future__ import annotations

from collections import defaultdict
import json
import os
import sys
import unicodedata

from history_probe import ProbeError, bearer_from_cookie, get_account_id, legacy_history_pages


class CatalogError(RuntimeError):
    pass


def normalized_title(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def read_anilist_catalog(database_url):
    """Read approved AniList mappings in a transaction that rejects writes."""
    if not database_url:
        raise CatalogError("MARQUEE_DATABASE_URL is missing")
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("set transaction read only")
                cur.execute("""select s.id::text, t.display_title, s.display_title,
                           array_remove(array[r.payload #>> '{media,title,romaji}',
                                              r.payload #>> '{media,title,english}',
                                              r.payload #>> '{media,title,native}'], null)
                    from public.marquee_source_mappings m
                    join public.marquee_seasons s on s.id=m.season_id
                    join public.marquee_titles t on t.id=s.show_title_id
                    left join public.marquee_ingest_raw r on r.source='anilist'
                        and r.source_entity_type='media_list' and r.payload->>'mediaId'=m.source_id
                    where m.source='anilist' and m.canonical_entity_type='season'""")
                seasons = cur.fetchall()
                cur.execute("""select t.id::text, t.display_title,
                           array_remove(array[r.payload #>> '{media,title,romaji}',
                                              r.payload #>> '{media,title,english}',
                                              r.payload #>> '{media,title,native}'], null)
                    from public.marquee_source_mappings m
                    join public.marquee_titles t on t.id=m.movie_title_id
                    left join public.marquee_ingest_raw r on r.source='anilist'
                        and r.source_entity_type='media_list' and r.payload->>'mediaId'=m.source_id
                    where m.source='anilist' and m.canonical_entity_type='movie'""")
                movies = cur.fetchall()
        return seasons, movies
    except Exception:
        # Driver errors can include connection details; never print them.
        raise CatalogError("Read-only AniList catalog lookup failed") from None


def compare(pages, seasons, movies):
    """Return counts of title candidates, never a durable source mapping."""
    by_season_title, by_show_title, by_movie_title = (defaultdict(set) for _ in range(3))
    for target, show_title, season_title, aliases in seasons:
        for value in (show_title, *aliases):
            if normalized_title(value):
                by_show_title[normalized_title(value)].add(target)
        for value in (season_title, *aliases):
            if normalized_title(value):
                by_season_title[normalized_title(value)].add(target)
    for target, title, aliases in movies:
        for value in (title, *aliases):
            if normalized_title(value):
                by_movie_title[normalized_title(value)].add(target)
    groups = defaultdict(lambda: {"episodes": 0, "season_titles": set(), "show_titles": set()})
    movie_panels = {}
    counts = defaultdict(int)
    for page in pages:
        for item in page:
            counts["observations"] += 1
            panel = item.get("panel")
            metadata = panel.get("episode_metadata") if isinstance(panel, dict) else None
            if not isinstance(metadata, dict) or not isinstance(panel.get("id"), str):
                counts["without_episode_metadata"] += 1
                if isinstance(panel, dict) and panel.get("type") == "movie" and isinstance(panel.get("id"), str):
                    movie_panels[panel["id"]] = normalized_title(panel.get("title"))
                continue
            series_id, season_id = metadata.get("series_id"), metadata.get("season_id")
            if not all(isinstance(value, str) and value for value in (series_id, season_id)):
                counts["episode_without_series_and_season_ids"] += 1
                continue
            key = (series_id, season_id)
            groups[key]["episodes"] += 1
            groups[key]["season_titles"].add(normalized_title(metadata.get("season_title")))
            groups[key]["show_titles"].add(normalized_title(metadata.get("series_title")))

    for group in groups.values():
        season_matches = set().union(*(by_season_title[name] for name in group["season_titles"] if name))
        show_matches = set().union(*(by_show_title[name] for name in group["show_titles"] if name))
        candidates = season_matches & show_matches if season_matches & show_matches else season_matches | show_matches
        if season_matches and show_matches and not (season_matches & show_matches):
            category = "conflicting_title_evidence"
        elif len(candidates) == 1:
            category = "one_title_candidate"
        elif candidates:
            category = "multiple_title_candidates"
        else:
            category = "no_title_candidate"
        counts[category + "_source_seasons"] += 1
        counts[category + "_observations"] += group["episodes"]
    for title in movie_panels.values():
        candidates = by_movie_title[title] if title else set()
        category = "one" if len(candidates) == 1 else "multiple" if candidates else "none"
        counts[category + "_movie_candidates"] += 1
    return {"observations": counts["observations"],
            "without_episode_metadata": counts["without_episode_metadata"],
            "episode_without_series_and_season_ids": counts["episode_without_series_and_season_ids"],
            "distinct_source_seasons": len(groups),
            "anilist_seasons_available": len(seasons),
            "anilist_movies_available": len(movies),
            "candidate_counts": {category: {"source_seasons": counts[category + "_source_seasons"],
                                            "observations": counts[category + "_observations"]}
                                 for category in ("one_title_candidate", "multiple_title_candidates",
                                                  "conflicting_title_evidence", "no_title_candidate")},
            "movie_panels_evaluated": len(movie_panels),
            "movie_title_candidates": {category: counts[category + "_movie_candidates"]
                                       for category in ("one", "multiple", "none")},
            "note": "Title matches are review candidates only; no source IDs or mappings were written."}


def main():
    try:
        seasons, movies = read_anilist_catalog(os.environ.get("MARQUEE_DATABASE_URL"))
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, _ = get_account_id(token)
        pages = list(legacy_history_pages(account_id, token))
        if not pages:
            raise CatalogError("Crunchyroll history is empty")
        result = compare(pages, seasons, movies)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ProbeError, CatalogError) as exc:
        print(f"Catalog overlap probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
