#!/usr/bin/env python3
"""Read-only episode/version identity diagnostics without logging history."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
import sys

from history_probe import ProbeError, bearer_from_cookie, get_account_id, legacy_history_pages
from catalog_overlap_probe import normalized_title, read_anilist_catalog, season_title_indexes, CatalogError


def identity_review(pages, seasons=()):
    counts = Counter()
    episodes_by_season_number = defaultdict(set)
    panels_by_identifier = defaultdict(set)
    panels_by_season = defaultdict(set)
    audio_by_season_number = defaultdict(set)
    names_by_season = defaultdict(lambda: {"show": set(), "season": set()})
    for page in pages:
        for item in page:
            counts["observations"] += 1
            panel = item.get("panel")
            metadata = panel.get("episode_metadata") if isinstance(panel, dict) else None
            if not isinstance(metadata, dict):
                counts["no_episode_metadata"] += 1
                continue
            panel_id = panel.get("id")
            series_id, season_id = metadata.get("series_id"), metadata.get("season_id")
            if not all(isinstance(value, str) and value for value in (panel_id, series_id, season_id)):
                counts["incomplete_source_ids"] += 1
                continue
            season = (series_id, season_id)
            panels_by_season[season].add(panel_id)
            names_by_season[season]["show"].add(normalized_title(metadata.get("series_title")))
            names_by_season[season]["season"].add(normalized_title(metadata.get("season_title")))
            counts["episode_observations_with_ids"] += 1
            identifier = metadata.get("identifier")
            if isinstance(identifier, str) and identifier:
                panels_by_identifier[identifier].add(panel_id)
                counts["observations_with_identifier"] += 1
            value = metadata.get("episode_number")
            if type(value) is int and value > 0:
                number = value
            elif isinstance(value, str) and value.isdecimal() and int(value) > 0:
                number = int(value)
            else:
                counts["missing_or_invalid_episode_number"] += 1
                continue
            key = (series_id, season_id, number)
            episodes_by_season_number[key].add(panel_id)
            locale = metadata.get("audio_locale")
            if isinstance(locale, str) and locale:
                audio_by_season_number[key].add(locale)
                counts["observations_with_audio_locale"] += 1
    collisions = {key: panel_ids for key, panel_ids in episodes_by_season_number.items()
                  if len(panel_ids) > 1}
    by_season_title, by_show_title = season_title_indexes(seasons)
    candidate_counts = Counter()
    for season, names in names_by_season.items():
        season_matches = set().union(*(by_season_title[name] for name in names["season"] if name))
        show_matches = set().union(*(by_show_title[name] for name in names["show"] if name))
        candidates = season_matches & show_matches if season_matches & show_matches else season_matches | show_matches
        if len(candidates) == 1 and not (season_matches and show_matches and not season_matches & show_matches):
            candidate_counts["one_title_candidate"] += 1
            if any(key[:2] == season for key in collisions):
                candidate_counts["one_candidate_with_episode_number_collision"] += 1
            if len([key for key in episodes_by_season_number if key[:2] == season]) < len(panels_by_season[season]):
                candidate_counts["one_candidate_with_missing_or_duplicate_numbers"] += 1
    return {"observations": counts["observations"],
            "no_episode_metadata": counts["no_episode_metadata"],
            "incomplete_source_ids": counts["incomplete_source_ids"],
            "episode_observations_with_ids": counts["episode_observations_with_ids"],
            "distinct_source_seasons": len(panels_by_season),
            "distinct_episode_panel_ids": len(set().union(*panels_by_season.values())) if panels_by_season else 0,
            "missing_or_invalid_episode_number": counts["missing_or_invalid_episode_number"],
            "distinct_season_episode_numbers": len(episodes_by_season_number),
            "season_episode_numbers_with_multiple_panel_ids": len(collisions),
            "panel_ids_at_colliding_numbers": sum(len(ids) for ids in collisions.values()),
            "source_seasons_with_number_collisions": len({key[:2] for key in collisions}),
            "observations_with_identifier": counts["observations_with_identifier"],
            "identifiers_shared_by_multiple_panel_ids": sum(len(ids) > 1 for ids in panels_by_identifier.values()),
            "observations_with_audio_locale": counts["observations_with_audio_locale"],
            "season_episode_numbers_with_multiple_audio_locales": sum(
                len(locales) > 1 for locales in audio_by_season_number.values()),
            "anilist_seasons_available": len(seasons),
            "one_title_candidate_source_seasons": candidate_counts["one_title_candidate"],
            "one_candidate_with_episode_number_collision": candidate_counts["one_candidate_with_episode_number_collision"],
            "one_candidate_with_missing_or_duplicate_numbers": candidate_counts["one_candidate_with_missing_or_duplicate_numbers"],
            "note": "Source IDs are stable within this feed; episode-number collisions are review evidence, not version mappings."}


def main():
    try:
        seasons, _ = read_anilist_catalog(os.environ.get("MARQUEE_DATABASE_URL"))
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, _ = get_account_id(token)
        pages = list(legacy_history_pages(account_id, token))
        result = identity_review(pages, seasons)
        if result["observations"] < 7933 or not result["episode_observations_with_ids"]:
            raise ProbeError("History coverage regressed or episode IDs are unavailable")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ProbeError, CatalogError) as exc:
        print(f"Identity review probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
