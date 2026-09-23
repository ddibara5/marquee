#!/usr/bin/env python3
"""Read-only pre-import integrity gate; prints aggregate counts only."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
import sys

from history_probe import ProbeError, bearer_from_cookie, get_account_id, legacy_history_pages


BASELINE = 7933
OLDEST_VERIFIED = datetime(2023, 10, 9, 0, 10, 48, tzinfo=timezone.utc)


def inspect(pages, *, minimum=BASELINE):
    """Consume the entire pagination iterator before accepting any observation."""
    counts = Counter()
    events = set()
    panels = {}
    oldest = newest = None
    for page in pages:
        counts["pages"] += 1
        if not page:
            raise ProbeError("History contains an unexpected empty page")
        for item in page:
            counts["observations"] += 1
            event_id = item.get("id")
            if not isinstance(event_id, str) or not event_id.strip():
                raise ProbeError("History event lacks a stable ID")
            if event_id in events:
                raise ProbeError("History contains duplicate event IDs")
            events.add(event_id)
            value = item.get("date_played")
            try:
                if not isinstance(value, str):
                    raise ValueError
                played = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if played.tzinfo is None:
                    raise ValueError
                played = played.astimezone(timezone.utc)
            except ValueError:
                raise ProbeError("History event has an invalid playback date") from None
            oldest = min(oldest, played) if oldest else played
            newest = max(newest, played) if newest else played
            panel = item.get("panel")
            if not isinstance(panel, dict) or not isinstance(panel.get("id"), str) or not panel["id"]:
                counts["without_panel_id"] += 1
                continue
            panel_id = panel["id"]
            metadata = panel.get("episode_metadata")
            if not isinstance(metadata, dict):
                counts["without_episode_metadata"] += 1
                continue
            series_id, season_id = metadata.get("series_id"), metadata.get("season_id")
            if not all(isinstance(v, str) and v for v in (series_id, season_id)):
                counts["without_series_or_season_id"] += 1
                continue
            number = metadata.get("episode_number")
            if type(number) is int and number > 0:
                pass
            elif isinstance(number, str) and number.isdecimal() and int(number) > 0:
                number = int(number)
            else:
                counts["without_usable_episode_number"] += 1
                number = None
            identity = (series_id, season_id, number)
            if panel_id in panels and panels[panel_id] != identity:
                raise ProbeError("Episode panel identity changed within the feed")
            panels[panel_id] = identity
            counts["with_source_episode_identity"] += 1
    if counts["observations"] < minimum:
        raise ProbeError("History count regressed below verified coverage")
    if minimum == BASELINE and oldest > OLDEST_VERIFIED:
        raise ProbeError("Oldest playback regressed despite the total event count")
    return {"coverage": "complete", "pages": counts["pages"],
            "events": counts["observations"], "unique_event_ids": len(events),
            "unique_panel_ids_with_identity": len(panels),
            "repeat_panel_observations": counts["with_source_episode_identity"] - len(panels),
            "without_panel_id": counts["without_panel_id"],
            "without_episode_metadata": counts["without_episode_metadata"],
            "without_series_or_season_id": counts["without_series_or_season_id"],
            "without_usable_episode_number": counts["without_usable_episode_number"],
            "oldest_playback_utc": oldest.isoformat(),
            "newest_playback_utc": newest.isoformat(),
            "importable_without_review": 0,
            "note": "Stable source IDs identify observations; no cross-provider mappings are inferred."}


def database_counts(database_url):
    if not database_url:
        raise ProbeError("MARQUEE_DATABASE_URL is missing")
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("set transaction read only")
                cur.execute("""select
                    (select count(*) from public.marquee_source_mappings where source='crunchyroll' and source_entity_type='episode'),
                    (select count(*) from public.marquee_watch_history_sources where source='crunchyroll'),
                    (select count(*) from public.marquee_watch_history_sources where source='trakt' and source_entity_type='episode'),
                    (select count(*) from public.marquee_mapping_review where source='crunchyroll' and status='open'),
                    (select count(*) from public.game_ranks),
                    (select count(*) from public.rank_comparisons)""")
                episode_mappings, source_links, trakt_links, open_reviews, game_ranks, comparisons = cur.fetchone()
        if (game_ranks, comparisons) != (53, 154):
            raise ProbeError("GameDeck baseline differs from verified values")
        return {"approved_crunchyroll_episode_mappings": episode_mappings,
                "crunchyroll_source_links": source_links,
                "trakt_episode_source_links": trakt_links,
                "open_crunchyroll_reviews": open_reviews,
                "game_ranks": game_ranks, "rank_comparisons": comparisons}
    except ProbeError:
        raise
    except Exception:
        raise ProbeError("Read-only database integrity check failed") from None


def main():
    try:
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, _ = get_account_id(token)
        result = inspect(legacy_history_pages(account_id, token))
        result["database"] = database_counts(os.environ.get("MARQUEE_DATABASE_URL"))
        print(json.dumps(result, sort_keys=True))
        return 0
    except ProbeError as exc:
        print(f"Crunchyroll import gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
