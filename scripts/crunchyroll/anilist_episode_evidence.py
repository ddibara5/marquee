#!/usr/bin/env python3
"""Read-only AniList episode-count corroboration; aggregate review evidence only."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import sys
from urllib.request import Request
from uuid import UUID

from history_probe import ProbeError, request_json
from season_review_queue import prepare
from staged_review import ReviewError, analyze, source_snapshot


QUERY = """query ($ids: [Int]) {
  Page(page: 1, perPage: 50) {
    pageInfo { hasNextPage }
    media(id_in: $ids, type: ANIME) {
      id episodes startDate { year }
    }
  }
}"""


def anilist_metadata(media_ids, *, requester=request_json):
    ids = sorted({int(v) for v in media_ids})
    if not ids or len(ids) > 50 or any(v <= 0 for v in ids):
        raise ReviewError("AniList candidate set changed shape")
    body = json.dumps({"query": QUERY, "variables": {"ids": ids}}).encode()
    request = Request("https://graphql.anilist.co", data=body, method="POST",
                      headers={"Content-Type": "application/json",
                               "Accept": "application/json",
                               "User-Agent": "MarqueeReviewProbe/1.0"})
    try:
        payload = requester(request)
    except ProbeError:
        raise ReviewError("AniList metadata lookup failed") from None
    page = payload.get("data", {}).get("Page") if isinstance(payload, dict) else None
    if (not isinstance(page, dict) or not isinstance(page.get("media"), list)
            or not isinstance(page.get("pageInfo"), dict)
            or page["pageInfo"].get("hasNextPage") is not False):
        raise ReviewError("AniList metadata response changed shape")
    result = {}
    for media in page["media"]:
        if not isinstance(media, dict) or type(media.get("id")) is not int:
            raise ReviewError("AniList media identity changed shape")
        media_id = media["id"]
        if media_id not in ids or media_id in result:
            raise ReviewError("AniList returned an unexpected media identity")
        episodes = media.get("episodes")
        if episodes is not None and (type(episodes) is not int or episodes < 1):
            raise ReviewError("AniList episode total changed shape")
        date = media.get("startDate")
        year = date.get("year") if isinstance(date, dict) else None
        if year is not None and (type(year) is not int or year < 1880 or year > 2200):
            raise ReviewError("AniList start year changed shape")
        result[media_id] = (episodes, year)
    if len(result) != len(ids):
        raise ReviewError("AniList candidate metadata is incomplete")
    return result


def evidence(records, review_rows, metadata):
    source = defaultdict(lambda: {"numbers": set(), "air_years": set()})
    for event in records:
        panel = event.get("panel")
        episode = panel.get("episode_metadata") if isinstance(panel, dict) else None
        if not isinstance(episode, dict):
            continue
        season = source[episode["season_id"]]
        number = episode.get("episode_number")
        if (type(number) is int or isinstance(number, str) and number.isdecimal()) and int(number) > 0:
            season["numbers"].add(int(number))
        air_date = episode.get("episode_air_date")
        if isinstance(air_date, str) and len(air_date) >= 4 and air_date[:4].isdigit():
            season["air_years"].add(int(air_date[:4]))
    out = defaultdict(int)
    for season_id, row in review_rows.items():
        if len(row["candidates"]) != 1 or season_id not in source:
            continue
        out["one_title_candidate_seasons"] += 1
        media_id = int(row["candidates"][0]["anilist_media_id"])
        total, year = metadata[media_id]
        numbers = source[season_id]["numbers"]
        years = source[season_id]["air_years"]
        if total is None:
            out["anilist_episode_total_unavailable"] += 1
        elif not numbers:
            out["no_usable_source_episode_number"] += 1
        elif max(numbers) <= total:
            out["observed_numbers_within_anilist_total"] += 1
            if max(numbers) == total:
                out["highest_observed_equals_anilist_total"] += 1
        else:
            out["observed_number_exceeds_anilist_total"] += 1
        if year is not None and years:
            if min(years) - 1 <= year <= max(years) + 1:
                out["year_near_episode_air_span"] += 1
                if total is not None and numbers and max(numbers) <= total:
                    out["year_and_number_both_compatible"] += 1
            else:
                out["year_outside_episode_air_span"] += 1
    return dict(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args(argv)
    try:
        scope = str(UUID(args.user_id))
        records, seasons, mappings, trakt = source_snapshot(
            os.environ.get("MARQUEE_DATABASE_URL"), scope)
        if analyze(records, seasons, mappings, trakt)["approved_crunchyroll_episode_mappings"]:
            raise ReviewError("Approved mappings exist; refresh candidate review")
        rows, _ = prepare(records, seasons)
        media_ids = {c["anilist_media_id"] for row in rows.values()
                     if len(row["candidates"]) == 1 for c in row["candidates"]}
        metadata = anilist_metadata(media_ids)
        print(json.dumps({"review_evidence": evidence(records, rows, metadata),
                          "anilist_media_checked": len(metadata),
                          "note": "Counts and years are review clues only; no mapping, date or watch was written."},
                         sort_keys=True))
        return 0
    except (ReviewError, ProbeError, ValueError, KeyError):
        print("Read-only AniList evidence check failed; no private records printed", file=sys.stderr)
        return 1
    except Exception:
        print("Read-only AniList evidence check failed; check connection, no private records printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
