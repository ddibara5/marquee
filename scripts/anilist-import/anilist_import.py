#!/usr/bin/env python3
"""Seed Marquee anime identity, statuses and scores from an AniList account."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


API_URL = "https://graphql.anilist.co"
# AniList currently documents a maximum of 11,000 recently updated unique
# entries for this full-list query. Reject the boundary rather than truncate.
MAX_ENTRIES = 11000
QUERY = """query MarqueeAnimeSeed($username: String!) {
  User(name: $username) { id name }
  MediaListCollection(userName: $username, type: ANIME) {
    lists {
      entries {
        id userId mediaId status score score10: score(format: POINT_10_DECIMAL)
        progress updatedAt private hiddenFromStatusLists
        media {
          id type format title { romaji english native }
          startDate { year }
          relations { edges { relationType node { id type } } }
        }
      }
    }
  }
}"""
STATUSES = {
    "CURRENT": "watching", "REPEATING": "watching",
    "PLANNING": "planned", "COMPLETED": "completed",
    "PAUSED": "on_hold", "DROPPED": "dropped",
}


class SourceError(RuntimeError):
    pass


class Review(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def positive_id(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SourceError(f"invalid {label}")
    return str(value)


def parse_score(value):
    if value is None:
        return Decimal("0")
    if isinstance(value, bool):
        raise SourceError("list entry has invalid score")
    try:
        score = Decimal(str(value))
    except InvalidOperation as exc:
        raise SourceError("list entry has invalid score") from exc
    if not score.is_finite() or not 0 <= score <= 10 or score != score.quantize(Decimal("0.1")):
        raise SourceError("list entry has invalid 10-point score")
    return score


def anime_relations(media):
    try:
        edges = media["relations"]["edges"]
        if not isinstance(edges, list):
            raise TypeError
        links = []
        for edge in edges:
            node = edge["node"]
            if node["type"] == "ANIME":
                links.append((positive_id(node["id"], "related anime ID"), edge["relationType"]))
            elif node["type"] != "MANGA":
                raise TypeError
        return links
    except (KeyError, TypeError) as exc:
        raise SourceError("anime relation graph is incomplete") from exc


def validate(response, username):
    if not isinstance(response, dict) or response.get("errors"):
        raise SourceError("AniList returned GraphQL errors")
    try:
        data = response["data"]
        user = data["User"]
        owner = positive_id(user["id"], "AniList user ID")
        if not isinstance(user["name"], str) or user["name"].casefold() != username.casefold():
            raise SourceError("AniList username differs from the requested account")
        groups = data["MediaListCollection"]["lists"]
        if not isinstance(groups, list):
            raise TypeError
        result = {}
        for group in groups:  # Include custom lists and split completed lists.
            if not isinstance(group["entries"], list):
                raise TypeError
            for entry in group["entries"]:
                entry_id = positive_id(entry["id"], "AniList list-entry ID")
                media_id = positive_id(entry["mediaId"], "AniList media ID")
                if positive_id(entry["userId"], "list owner") != owner:
                    raise SourceError("list entry belongs to another AniList user")
                media = entry["media"]
                if positive_id(media["id"], "media ID") != media_id or media["type"] != "ANIME":
                    raise SourceError("list media identity conflicts with entry")
                if entry["status"] not in STATUSES:
                    raise SourceError(f"unknown AniList status for entry {entry_id}")
                parse_score(entry["score10"])
                if entry.get("updatedAt") not in (None, 0):
                    positive_id(entry["updatedAt"], "list update timestamp")
                anime_relations(media)
                if entry_id in result and result[entry_id] != entry:
                    raise SourceError("conflicting duplicate list entry across groups")
                result[entry_id] = entry
        if not result or len(result) >= MAX_ENTRIES:
            raise SourceError("AniList returned an empty list or reached its full-list limit")
        media_ids = [entry["mediaId"] for entry in result.values()]
        if len(media_ids) != len(set(media_ids)):
            raise SourceError("two list entries point to one AniList media ID")
        return {"user": {"id": owner, "name": user["name"]},
                "entries": list(result.values()), "fetched_at": datetime.now(timezone.utc)}
    except (KeyError, TypeError) as exc:
        raise SourceError("AniList list response shape changed") from exc


def fetch(username, token=None, opener=urlopen, sleep=time.sleep):
    body = encoded({"query": QUERY, "variables": {"username": username}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "MarqueeAniListSeed/1.0 (github.com/ddibara5/marquee)"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API_URL, data=body, headers=headers, method="POST")
    for attempt in range(5):
        try:
            with opener(request, timeout=30) as reply:
                payload = json.load(reply)
                return validate(payload, username)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise SourceError(f"AniList HTTP {exc.code}") from None
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            delay = int(retry_after) if retry_after.isdigit() else min(30, 2 ** attempt)
            if delay > 120:
                raise SourceError("AniList rate limit exceeds retry window")
            sleep(delay + random.random() * 0.1)
        except (URLError, TimeoutError) as exc:
            if attempt == 4:
                raise SourceError("AniList transport failed") from exc
            sleep(min(30, 2 ** attempt))
    raise AssertionError("retry loop exhausted")


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()


def target(cur, media_id):
    row = one(cur, """select canonical_entity_type,title_id,show_title_id,movie_title_id,season_id
        from public.marquee_source_mappings
        where source='anilist' and source_entity_type='media' and source_id=%s""", (media_id,))
    if row is None:
        return None
    kind, title_id, show_id, movie_id, season_id = row
    if kind == "season" and season_id:
        valid = one(cur, """select t.is_anime from public.marquee_seasons s
            join public.marquee_shows sh on sh.title_id=s.show_title_id
            join public.marquee_titles t on t.id=sh.title_id where s.id=%s""", (season_id,))
        return ("season_id", season_id) if valid and valid[0] else None
    if kind in ("title", "show", "movie"):
        title = {"title": title_id, "show": show_id, "movie": movie_id}[kind]
        valid = one(cur, "select media_type,is_anime from public.marquee_titles where id=%s", (title,))
        return ("title_id", title) if valid and valid[1] and (kind == "title" or valid[0] == kind) else None
    return None


def resolve(cur, entry):
    media = entry["media"]
    media_id = str(entry["mediaId"])
    existing = target(cur, media_id)
    if existing:
        return existing
    # A mapping that exists but points to an incompatible target is a review,
    # never a reason to create a second canonical title.
    if one(cur, """select 1 from public.marquee_source_mappings
        where source='anilist' and source_entity_type='media' and source_id=%s""", (media_id,)):
        raise Review("existing AniList mapping conflicts with anime catalog")
    if anime_relations(media):
        raise Review("anime relations require franchise review before catalog creation")
    fmt = media.get("format")
    if fmt not in ("TV", "TV_SHORT", "OVA", "ONA", "SPECIAL", "MOVIE"):
        raise Review("anime format requires catalog review")
    titles = media["title"]
    display = next((titles.get(key).strip() for key in ("romaji", "english", "native")
                    if isinstance(titles.get(key), str) and titles.get(key).strip()), None)
    if not display:
        raise Review("anime has no display title")
    year = media.get("startDate", {}).get("year") if media.get("startDate") else None
    if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1880 <= year <= 2200):
        raise Review("invalid anime release year")
    kind = "movie" if fmt == "MOVIE" else "show"
    title_id = one(cur, """insert into public.marquee_titles
        (media_type,display_title,is_anime,release_year) values (%s,%s,true,%s) returning id""",
        (kind, display, year))[0]
    if kind == "movie":
        cur.execute("insert into public.marquee_movies (title_id) values (%s)", (title_id,))
        cur.execute("""insert into public.marquee_source_mappings
            (source,source_entity_type,source_id,canonical_entity_type,movie_title_id,match_method,rule_id)
            values ('anilist','media',%s,'movie',%s,'rule','standalone-no-anime-relations-v1')""",
            (media_id, title_id))
        return ("title_id", title_id)
    cur.execute("insert into public.marquee_shows (title_id) values (%s)", (title_id,))
    season_id = one(cur, """insert into public.marquee_seasons
        (show_title_id,display_title) values (%s,%s) returning id""", (title_id, display))[0]
    cur.execute("""insert into public.marquee_source_mappings
        (source,source_entity_type,source_id,canonical_entity_type,season_id,match_method,rule_id)
        values ('anilist','media',%s,'season',%s,'rule','standalone-no-anime-relations-v1')""",
        (media_id, season_id))
    return ("season_id", season_id)


def seed(cur, user_id, entry, column, entity_id):
    # The column comes only from target()/resolve(), never external JSON.
    updated = datetime.fromtimestamp(entry["updatedAt"], timezone.utc) if entry.get("updatedAt") else None
    cur.execute(f"""insert into public.marquee_statuses
        (user_id,{column},status,source,source_record_id,source_updated_at)
        values (%s,%s,%s,'anilist',%s,%s)
        on conflict (user_id,{column}) where {column} is not null do nothing""",
        (user_id, entity_id, STATUSES[entry["status"]], str(entry["id"]), updated))
    inserted = cur.rowcount
    score = parse_score(entry["score10"])
    if score:
        cur.execute(f"""insert into public.marquee_ratings
            (user_id,{column},score,source,source_record_id,source_updated_at)
            values (%s,%s,%s,'anilist',%s,%s)
            on conflict (user_id,{column}) where {column} is not null do nothing""",
            (user_id, entity_id, score, str(entry["id"]), updated))
        inserted += cur.rowcount
    return inserted


def run(conn, get_snapshot, user_id):
    scope = str(UUID(user_id))
    counts = {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "unmapped": 0}
    with conn.transaction():
        with conn.cursor() as cur:
            run_id = one(cur, """insert into public.marquee_sync_runs (source,user_id,scope_key)
                values ('anilist',%s,%s) returning id""", (scope, scope))[0]
    try:
        snapshot = get_snapshot()
        with conn.transaction():
            with conn.cursor() as cur:
                for entry in snapshot["entries"]:
                    counts["fetched"] += 1
                    media_id = str(entry["mediaId"])
                    entry_id = str(entry["id"])
                    payload = encoded(entry)
                    cur.execute("""insert into public.marquee_ingest_raw
                        (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,
                         payload_hash,payload,first_sync_run_id)
                        values ('anilist','media_list',%s,%s,%s,%s,%s,%s::jsonb,%s)
                        on conflict (scope_key,source,source_entity_type,dedupe_key)
                        do update set payload_hash=excluded.payload_hash,payload=excluded.payload,
                        last_seen_at=now()""",
                        (entry_id, scope, scope, entry_id, hashlib.sha256(payload.encode()).hexdigest(), payload, run_id))
                    try:
                        # A failed catalog attempt cannot leave an orphan before
                        # raw evidence and review are committed.
                        with conn.transaction():
                            column, entity_id = resolve(cur, entry)
                            inserted = seed(cur, scope, entry, column, entity_id)
                    except Review as exc:
                        titles = entry["media"]["title"]
                        source_title = next((titles.get(k) for k in ("romaji", "english", "native") if titles.get(k)), None)
                        cur.execute("""insert into public.marquee_mapping_review
                            (source,source_entity_type,source_id,source_title,reason)
                            values ('anilist','media',%s,%s,%s)
                            on conflict (source,source_entity_type,source_id) where status='open'
                            do update set source_title=excluded.source_title,reason=excluded.reason""",
                            (media_id, source_title, str(exc)))
                        counts["unmapped"] += 1
                        status = "review"
                    else:
                        counts["inserted" if inserted else "skipped"] += 1
                        cur.execute("""update public.marquee_mapping_review set status='resolved',
                            resolved_at=now(),resolved_mapping_id=(select id from public.marquee_source_mappings
                            where source='anilist' and source_entity_type='media' and source_id=%s),
                            resolution_notes='Resolved by stable AniList ID'
                            where source='anilist' and source_entity_type='media' and source_id=%s and status='open'""",
                            (media_id, media_id))
                        status = "mapped"
                    cur.execute("""update public.marquee_ingest_raw set normalization_status=%s,
                        normalization_error=null where scope_key=%s and source='anilist'
                        and source_entity_type='media_list' and dedupe_key=%s""", (status, scope, entry_id))
                cur.execute("""update public.marquee_sync_runs set status='succeeded',finished_at=now(),
                    fetched_count=%s,inserted_count=%s,updated_count=%s,skipped_count=%s,unmapped_count=%s
                    where id=%s and status='running'""", (*counts.values(), run_id))
                if cur.rowcount != 1:
                    raise SourceError("AniList sync run could not finish")
                checkpoint = encoded({"completed_at": snapshot["fetched_at"].isoformat(),
                                      "account_id": snapshot["user"]["id"],
                                      "entries": len(snapshot["entries"])})
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,watermark,last_attempt_at,last_success_at,last_success_run_id)
                    values ('anilist',%s,%s,%s::jsonb,now(),now(),%s)
                    on conflict (source,scope_key) do update set watermark=excluded.watermark,
                    last_attempt_at=now(),last_success_at=now(),last_success_run_id=excluded.last_success_run_id,
                    last_error=null,consecutive_failures=0,updated_at=now()""",
                    (scope, scope, checkpoint, run_id))
        return counts
    except Exception as exc:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""update public.marquee_sync_runs set status='failed',finished_at=now(),
                    error_count=1,error_summary=%s where id=%s and status='running'""", (str(exc)[:500], run_id))
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,last_attempt_at,last_error,consecutive_failures)
                    values ('anilist',%s,%s,now(),%s,1)
                    on conflict (source,scope_key) do update set last_attempt_at=now(),last_error=excluded.last_error,
                    consecutive_failures=public.marquee_sync_state.consecutive_failures+1,updated_at=now()""",
                    (scope, scope, str(exc)[:500]))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="AniList username (public profile name)")
    parser.add_argument("--user-id", required=True, help="Existing Supabase auth.users UUID")
    parser.add_argument("--fixture", type=Path, help="Offline GraphQL response JSON")
    parser.add_argument("--dry-run", action="store_true", help="Validate list, no database writes")
    parser.add_argument("--accept-public-list", action="store_true",
                        help="Acknowledge public list queries can omit private entries")
    args = parser.parse_args(argv)
    user_id = str(UUID(args.user_id))
    token = os.environ.get("ANILIST_ACCESS_TOKEN")
    if not args.fixture and not token and not args.accept_public_list:
        parser.error("provide ANILIST_ACCESS_TOKEN securely or opt in to a public-only list")
    get_snapshot = (lambda: validate(json.loads(args.fixture.read_text()), args.username)) if args.fixture else (
        lambda: fetch(args.username, token))
    if args.dry_run:
        snapshot = get_snapshot()
        linked = sum(bool(anime_relations(entry["media"])) for entry in snapshot["entries"])
        print(json.dumps({"validated": len(snapshot["entries"]), "related_needing_review": linked,
                          "account_id": snapshot["user"]["id"]}))
        return 0
    database_url = os.environ.get("MARQUEE_DATABASE_URL")
    if not database_url:
        parser.error("MARQUEE_DATABASE_URL required for import")
    try:
        import psycopg
    except ImportError:
        parser.error("install scripts/trakt-sync/requirements.txt first")
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            locked = one(cur, "select pg_try_advisory_lock(hashtext('marquee.anilist'),hashtext(%s))", (user_id,))
            if not locked[0]:
                raise SourceError("another AniList import is active for this user")
        try:
            counts = run(conn, get_snapshot, user_id)
        finally:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_unlock(hashtext('marquee.anilist'),hashtext(%s))", (user_id,))
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SourceError, ValueError, OSError) as exc:
        print(f"AniList import failed: {exc}", file=sys.stderr)
        sys.exit(1)
