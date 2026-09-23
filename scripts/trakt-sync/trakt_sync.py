#!/usr/bin/env python3
"""Import a complete Trakt snapshot into Marquee. No network or DB I/O at import time."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID


FEEDS = {
    "history_movies": "/sync/history/movies",
    "history_episodes": "/sync/history/episodes",
    "ratings_movies": "/sync/ratings/movies",
    "ratings_shows": "/sync/ratings/shows",
    "watchlist_movies": "/sync/watchlist/movies",
    "watchlist_shows": "/sync/watchlist/shows",
}
MAX_PAGES = 10000


class SourceError(RuntimeError):
    pass


def stable_id(value):
    if value is None or isinstance(value, bool) or not str(value).strip():
        raise SourceError("source record has no stable ID")
    return str(value)


def timestamp(value):
    if not isinstance(value, str):
        raise SourceError("source record has no timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise SourceError("invalid source timestamp") from exc


def identity(feed, item):
    if not isinstance(item, dict):
        raise SourceError(f"{feed}: expected an object")
    kind = "movie" if feed.endswith("movies") else "show"
    if feed == "history_episodes":
        kind = "episode"
    media = item.get(kind)
    if not isinstance(media, dict) or not isinstance(media.get("ids"), dict):
        raise SourceError(f"{feed}: missing {kind} IDs")
    media_id = stable_id(media["ids"].get("trakt"))
    if feed.startswith("history_"):
        key = stable_id(item.get("id"))
        at = timestamp(item.get("watched_at"))
    elif feed.startswith("ratings_"):
        key = media_id
        at = timestamp(item.get("rated_at"))
        score = item.get("rating")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 10:
            raise SourceError("Trakt rating outside 1..10")
    else:
        key = media_id
        at = timestamp(item.get("listed_at"))
    if kind == "episode":
        show = item.get("show")
        if not isinstance(show, dict) or not isinstance(show.get("ids"), dict):
            raise SourceError("episode history missing show IDs")
        stable_id(show["ids"].get("trakt"))
    return kind, media_id, key, at


def encoded(item):
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class Snapshot:
    feeds: dict
    fetched_at: datetime

    def validate(self):
        if set(self.feeds) != set(FEEDS):
            raise SourceError("snapshot requires all six feeds")
        for name, items in self.feeds.items():
            if not isinstance(items, list):
                raise SourceError(f"{name}: expected a list")
            seen = set()
            for item in items:
                _, _, key, _ = identity(name, item)
                if key in seen:
                    raise SourceError(f"{name}: duplicate source record {key}; pagination may have shifted")
                seen.add(key)
        return self


class TraktHTTP:
    def __init__(self, client_id, access_token, *, opener=urlopen, sleep=time.sleep):
        self.client_id, self.access_token = client_id, access_token
        self.opener, self.sleep = opener, sleep

    def page(self, feed, page, limit):
        url = "https://api.trakt.tv" + FEEDS[feed] + "?" + urlencode({"page": page, "limit": limit})
        request = Request(url, headers={
            "trakt-api-key": self.client_id,
            "trakt-api-version": "2",
            "Authorization": "Bearer " + self.access_token,
            "Content-Type": "application/json",
            # Trakt sits behind Cloudflare, which 403s (error 1010) requests
            # without a recognizable User-Agent. Verified 2026-09-23.
            "User-Agent": "MarqueeTraktSync/1.0 (github.com/ddibara5/marquee)",
        })
        for attempt in range(5):
            try:
                with self.opener(request, timeout=30) as response:
                    if response.status != 200:
                        raise SourceError(f"{feed}: unexpected HTTP {response.status}")
                    body = json.load(response)
                    headers = response.headers
                if not isinstance(body, list):
                    raise SourceError(f"{feed}: expected a JSON list")
                try:
                    current = int(headers["X-Pagination-Page"])
                    pages = int(headers["X-Pagination-Page-Count"])
                    count = int(headers["X-Pagination-Item-Count"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise SourceError(f"{feed}: missing pagination metadata") from exc
                if current != page or pages < 0 or count < 0 or pages > MAX_PAGES:
                    raise SourceError(f"{feed}: inconsistent pagination metadata")
                if count and (pages < page or not body):
                    raise SourceError(f"{feed}: truncated page {page}")
                if not count and (pages not in (0, 1) or body):
                    raise SourceError(f"{feed}: inconsistent empty response")
                return body, pages, count
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise SourceError(f"{feed}: HTTP {exc.code}") from None
                delay = exc.headers.get("Retry-After") if exc.headers else None
                seconds = max(0, int(delay)) if delay and delay.isdigit() else min(30, 2 ** attempt)
                if seconds > 120:
                    raise SourceError(f"{feed}: rate limited; retry after {seconds} seconds")
                self.sleep(seconds + random.random() * 0.1)
            except (URLError, TimeoutError) as exc:
                if attempt == 4:
                    raise SourceError(f"{feed}: transport failure") from exc
                self.sleep(min(30, 2 ** attempt))
        raise AssertionError("retry loop exhausted")

    def fetch(self, limit=100):
        result = {}
        for feed in FEEDS:
            items = []
            page = 1
            expected = None
            while True:
                batch, pages, count = self.page(feed, page, limit)
                if expected is None:
                    expected = count
                elif expected != count:
                    raise SourceError(f"{feed}: item count changed during pagination; retry whole run")
                items.extend(batch)
                if page >= pages:
                    if len(items) != count:
                        raise SourceError(f"{feed}: expected {count} records, received {len(items)}")
                    break
                page += 1
            result[feed] = items
        return Snapshot(result, datetime.now(timezone.utc)).validate()


def fixture_snapshot(directory):
    feeds = {feed: json.loads((directory / (feed + ".json")).read_text()) for feed in FEEDS}
    return Snapshot(feeds, datetime.now(timezone.utc)).validate()


class Review(Exception):
    def __init__(self, reason):
        self.reason = reason


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()


def mapping(cur, source, kind, source_id):
    return one(cur, """select canonical_entity_type, title_id, show_title_id, movie_title_id, season_id, episode_id
        from public.marquee_source_mappings where source=%s and source_entity_type=%s and source_id=%s""",
        (source, kind, source_id))


def mapping_target(row):
    return next(str(value) for value in row[1:] if value is not None)


def add_mapping(cur, source, kind, source_id, target_type, target_id, method="external_id"):
    target_col = {"title": "title_id", "show": "show_title_id", "movie": "movie_title_id", "season": "season_id", "episode": "episode_id"}[target_type]
    existing = mapping(cur, source, kind, source_id)
    if existing:
        if mapping_target(existing) != str(target_id):
            raise Review("conflicting stable external ID")
        return
    # target_col comes from the fixed allowlist above, never from a source response.
    cur.execute(f"""insert into public.marquee_source_mappings
        (source, source_entity_type, source_id, canonical_entity_type, {target_col}, match_method)
        values (%s,%s,%s,%s,%s,%s)""", (source, kind, source_id, target_type, target_id, method))


def resolve_catalog(cur, kind, media, approved_shows):
    ids = media["ids"]
    trakt_id = stable_id(ids.get("trakt"))
    current = mapping(cur, "trakt", kind, trakt_id)
    candidates = set()
    for source in ("tmdb", "imdb"):
        if ids.get(source) is not None:
            row = mapping(cur, source, kind, str(ids[source]))
            if row:
                candidates.add(mapping_target(row))
    if current:
        if current[0] not in (kind, "title"):
            raise Review("Trakt mapping points to a different entity type")
        candidates.add(mapping_target(current))
    if len(candidates) > 1:
        raise Review("external IDs point to different canonical records")
    target = next(iter(candidates), None)
    if kind == "show" and target is None and trakt_id not in approved_shows:
        raise Review("TV show not approved as non-anime")
    if target is not None:
        row = one(cur, "select media_type, is_anime from public.marquee_titles where id=%s", (target,))
        if not row or row[0] != kind or (kind == "show" and row[1]):
            raise Review("existing catalog identity conflicts with Trakt media type or anime boundary")
        if not one(cur, f"select 1 from public.marquee_{'movies' if kind == 'movie' else 'shows'} where title_id=%s", (target,)):
            raise Review("existing title lacks its movie/show catalog row")
    else:
        title = media.get("title")
        if not isinstance(title, str) or not title.strip():
            raise Review("missing display title")
        year = media.get("year")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1880 <= year <= 2200):
            raise Review("invalid release year")
        target = one(cur, "insert into public.marquee_titles (media_type, display_title, release_year) values (%s,%s,%s) returning id",
                     (kind, title, year))[0]
        cur.execute(f"insert into public.marquee_{'movies' if kind == 'movie' else 'shows'} (title_id) values (%s)", (target,))
    add_mapping(cur, "trakt", kind, trakt_id, kind, target)
    for source in ("tmdb", "imdb"):
        if ids.get(source) is not None:
            add_mapping(cur, source, kind, str(ids[source]), kind, target)
    return target


def resolve_episode(cur, item, approved_shows):
    show_id = resolve_catalog(cur, "show", item["show"], approved_shows)
    episode = item["episode"]
    number = episode.get("number")
    season = episode.get("season")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise Review("episode lacks a positive episode number")
    if isinstance(season, bool) or not isinstance(season, int) or season < 0:
        raise Review("episode lacks a nonnegative season number")
    existing = mapping(cur, "trakt", "episode", stable_id(episode["ids"].get("trakt")))
    season_id = one(cur, "select id from public.marquee_seasons where show_title_id=%s and season_number=%s", (show_id, season))
    if not season_id:
        season_id = one(cur, "insert into public.marquee_seasons (show_title_id,season_number) values (%s,%s) returning id", (show_id, season))
    season_id = season_id[0]
    target = one(cur, "select id from public.marquee_episodes where season_id=%s and episode_number=%s", (season_id, number))
    if existing and target and mapping_target(existing) != str(target[0]):
        raise Review("episode ID conflicts with episode number")
    if existing and not target:
        raise Review("mapped episode moved to a different number")
    if target:
        target = target[0]
        other = one(cur, """select 1 from public.marquee_source_mappings where source='trakt'
            and source_entity_type='episode' and episode_id=%s and source_id<>%s""", (target, stable_id(episode["ids"].get("trakt"))))
        if other:
            raise Review("another stable episode ID uses this number")
    else:
        target = one(cur, "insert into public.marquee_episodes (season_id,episode_number,display_title) values (%s,%s,%s) returning id",
                     (season_id, number, episode.get("title")))[0]
    add_mapping(cur, "trakt", "episode", stable_id(episode["ids"].get("trakt")), "episode", target)
    return target


def normalize(cur, user_id, feed, item, approved_shows):
    kind, media_id, key, at = identity(feed, item)
    if kind == "episode":
        target = resolve_episode(cur, item, approved_shows)
    else:
        target = resolve_catalog(cur, kind, item[kind], approved_shows)
    if feed.startswith("history_"):
        entity = "movie" if kind == "movie" else "episode"
        logical_key = f"trakt:{entity}:{key}"
        column = "movie_title_id" if kind == "movie" else "episode_id"
        current = one(cur, """select history_id from public.marquee_watch_history_sources
            where user_id=%s and source='trakt' and source_entity_type=%s and source_record_id=%s""", (user_id, entity, key))
        if current:
            cur.execute("""update public.marquee_watch_history set watched_at=%s,source_updated_at=%s,updated_at=now()
                where user_id=%s and id=%s and source='trakt' and watched_at is distinct from %s""",
                (at, at, user_id, current[0], at))
            return "updated" if cur.rowcount else "skipped"
        history_id = one(cur, f"""insert into public.marquee_watch_history
            (user_id,{column},logical_event_key,watched_at,source,source_record_id,source_updated_at)
            values (%s,%s,%s,%s,'trakt',%s,%s)
            on conflict (user_id,logical_event_key) do update set source_updated_at=excluded.source_updated_at
            returning id""", (user_id, target, logical_key, at, key, at))[0]
        cur.execute("""insert into public.marquee_watch_history_sources
            (user_id,history_id,source,source_entity_type,source_record_id,observed_at)
            values (%s,%s,'trakt',%s,%s,%s) on conflict do nothing""", (user_id, history_id, entity, key, at))
        return "inserted"
    if feed.startswith("ratings_"):
        current = one(cur, "select id,source,manual_locked,source_updated_at from public.marquee_ratings where user_id=%s and title_id=%s", (user_id, target))
        if current and (current[2] or current[1] == "manual" or (current[3] and current[3] > at)):
            return "skipped"
        cur.execute("""insert into public.marquee_ratings (user_id,title_id,score,source,source_record_id,source_updated_at)
            values (%s,%s,%s,'trakt',%s,%s)
            on conflict (user_id,title_id) where title_id is not null do update
            set score=excluded.score, source='trakt',source_record_id=excluded.source_record_id,
                source_updated_at=excluded.source_updated_at,updated_at=now()
            where public.marquee_ratings.manual_locked=false and public.marquee_ratings.source <> 'manual'
                and (public.marquee_ratings.source_updated_at is null
                     or public.marquee_ratings.source_updated_at <= excluded.source_updated_at)""",
            (user_id, target, item["rating"], media_id, at))
        return "updated" if current else "inserted"
    if kind == "movie" or kind == "show":
        current = one(cur, "select source,manual_locked from public.marquee_watchlist where user_id=%s and title_id=%s", (user_id, target))
        if current and (current[1] or current[0] == "manual"):
            return "skipped"
        cur.execute("""insert into public.marquee_watchlist
            (user_id,title_id,source,source_record_id,source_updated_at,added_at)
            values (%s,%s,'trakt',%s,%s,%s)
            on conflict (user_id,title_id) do update set source='trakt',source_record_id=excluded.source_record_id,
                source_updated_at=excluded.source_updated_at,updated_at=now()
            where public.marquee_watchlist.manual_locked=false and public.marquee_watchlist.source <> 'manual'""",
            (user_id, target, media_id, at, at))
        return "updated" if current else "inserted"
    raise SourceError("unexpected feed")


def review(cur, kind, source_id, media, reason):
    cur.execute("""insert into public.marquee_mapping_review
        (source,source_entity_type,source_id,source_title,reason)
        values ('trakt',%s,%s,%s,%s)
        on conflict (source,source_entity_type,source_id) where status='open'
        do update set reason=excluded.reason,source_title=excluded.source_title""",
        (kind, source_id, media.get("title"), reason))


def run(conn, get_snapshot, user_id, approved_shows):
    scope = str(UUID(user_id))
    counts = {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "unmapped": 0}
    # Session lock covers both fetching and writing when caller holds it. This
    # transaction inserts the run separately so a failed attempt remains visible.
    with conn.transaction():
        with conn.cursor() as cur:
            state = one(cur, "select watermark from public.marquee_sync_state where source='trakt' and scope_key=%s", (scope,))
            old_watermark = state[0] if state else {}
            run_id = one(cur, """insert into public.marquee_sync_runs (source,user_id,scope_key)
                values ('trakt',%s,%s) returning id""", (scope, scope))[0]
    try:
        snapshot = get_snapshot().validate()
        with conn.transaction():
            with conn.cursor() as cur:
                seen_watchlist = set()
                watchlist_reviewed = False
                for feed, items in snapshot.feeds.items():
                    for item in items:
                        kind, media_id, key, _at = identity(feed, item)
                        counts["fetched"] += 1
                        payload = encoded(item)
                        digest = hashlib.sha256(payload.encode()).hexdigest()
                        cur.execute("""insert into public.marquee_ingest_raw
                            (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,payload_hash,payload,first_sync_run_id)
                            values ('trakt',%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                            on conflict (scope_key,source,source_entity_type,dedupe_key)
                            do update set payload_hash=excluded.payload_hash,payload=excluded.payload,last_seen_at=now()""",
                            (feed, media_id, scope, scope, key, digest, payload, run_id))
                        try:
                            # A savepoint removes catalog/mapping writes made before a
                            # later identity conflict while keeping raw evidence.
                            with conn.transaction():
                                inserted = normalize(cur, scope, feed, item, approved_shows)
                        except Review as exc:
                            media = item.get("episode" if kind == "episode" else kind, {})
                            review(cur, kind, media_id, media, exc.reason)
                            status = "review"
                            counts["unmapped"] += 1
                            if feed.startswith("watchlist_"):
                                watchlist_reviewed = True
                        else:
                            status = "mapped"
                            counts[inserted] += 1
                            match = mapping(cur, "trakt", kind, media_id)
                            if match:
                                cur.execute("""update public.marquee_mapping_review set status='resolved',
                                    resolved_at=now(),resolved_mapping_id=(select id from public.marquee_source_mappings
                                    where source='trakt' and source_entity_type=%s and source_id=%s),
                                    resolution_notes='Resolved by stable source mapping'
                                    where source='trakt' and source_entity_type=%s and source_id=%s and status='open'""",
                                    (kind, media_id, kind, media_id))
                            if feed.startswith("watchlist_"):
                                seen_watchlist.add(mapping_target(match))
                        cur.execute("""update public.marquee_ingest_raw set normalization_status=%s,normalization_error=null
                            where scope_key=%s and source='trakt' and source_entity_type=%s and dedupe_key=%s""",
                            (status, scope, feed, key))
                # Reconcile removals only when the complete watchlist was fetched
                # and every identity was resolved. Leave manual rows untouched.
                if not watchlist_reviewed:
                    cur.execute("""delete from public.marquee_watchlist
                        where user_id=%s and source='trakt' and manual_locked=false
                        and not (title_id = any(%s::uuid[]))""", (scope, list(seen_watchlist)))
                    counts["updated"] += cur.rowcount
                # No source timestamp is a safe incremental cursor for ratings and
                # watchlist removals. Re-fetch all six feeds each run. Watermark is
                # an audit marker, never a filter over source records.
                watermark = {"completed_at": snapshot.fetched_at.isoformat(), "feeds": {k: len(v) for k, v in snapshot.feeds.items()}}
                if old_watermark.get("completed_at") and watermark["completed_at"] < old_watermark["completed_at"]:
                    raise SourceError("refusing to move checkpoint backward")
                cur.execute("""update public.marquee_sync_runs set status='succeeded',finished_at=now(),
                    fetched_count=%s,inserted_count=%s,updated_count=%s,skipped_count=%s,unmapped_count=%s
                    where id=%s and status='running'""", (*counts.values(), run_id))
                if cur.rowcount != 1:
                    raise SourceError("sync run did not finish")
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,watermark,last_attempt_at,last_success_at,last_success_run_id)
                    values ('trakt',%s,%s,%s::jsonb,now(),now(),%s)
                    on conflict (source,scope_key) do update set watermark=excluded.watermark,
                    last_attempt_at=now(),last_success_at=now(),last_success_run_id=excluded.last_success_run_id,
                    last_error=null,consecutive_failures=0,updated_at=now()""", (scope, scope, json.dumps(watermark), run_id))
        return counts
    except Exception as exc:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""update public.marquee_sync_runs set status='failed',finished_at=now(),
                    error_count=1,error_summary=%s where id=%s and status='running'""", (str(exc)[:500], run_id))
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,last_attempt_at,last_error,consecutive_failures)
                    values ('trakt',%s,%s,now(),%s,1)
                    on conflict (source,scope_key) do update set last_attempt_at=now(),last_error=excluded.last_error,
                    consecutive_failures=public.marquee_sync_state.consecutive_failures+1,updated_at=now()""",
                    (scope, scope, str(exc)[:500]))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Existing Supabase auth.users UUID")
    parser.add_argument("--fixture-dir", type=Path, help="Offline input with all six feed JSON files")
    parser.add_argument("--approved-shows", type=Path, help="JSON array of vetted non-anime Trakt show IDs")
    parser.add_argument("--dry-run", action="store_true", help="Validate source without connecting to Supabase")
    args = parser.parse_args(argv)
    user_id = str(UUID(args.user_id))
    approved = set()
    if args.approved_shows:
        ids = json.loads(args.approved_shows.read_text())
        if not isinstance(ids, list):
            parser.error("approved-shows must be a JSON array")
        approved = {stable_id(value) for value in ids}
    if args.fixture_dir:
        fetch = lambda: fixture_snapshot(args.fixture_dir)
    else:
        client_id, token = os.environ.get("TRAKT_CLIENT_ID"), os.environ.get("TRAKT_ACCESS_TOKEN")
        if not client_id or not token:
            parser.error("TRAKT_CLIENT_ID and TRAKT_ACCESS_TOKEN are required for live fetch")
        fetch = TraktHTTP(client_id, token).fetch
    if args.dry_run:
        snapshot = fetch()
        print(json.dumps({"validated": {k: len(v) for k, v in snapshot.feeds.items()}}))
        return 0
    database_url = os.environ.get("MARQUEE_DATABASE_URL")
    if not database_url:
        parser.error("MARQUEE_DATABASE_URL required for import")
    try:
        import psycopg
    except ImportError:
        parser.error("install the pinned requirements first")
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            row = one(cur, "select pg_try_advisory_lock(hashtext('marquee.trakt'),hashtext(%s))", (user_id,))
            if not row[0]:
                raise SourceError("another Trakt run is already active for this user")
        try:
            counts = run(conn, fetch, user_id, approved)
        finally:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_unlock(hashtext('marquee.trakt'),hashtext(%s))", (user_id,))
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (SourceError, ValueError, OSError) as exc:
        print(f"Trakt sync failed: {exc}", file=sys.stderr)
        sys.exit(1)
