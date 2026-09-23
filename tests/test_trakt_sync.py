"""Offline Trakt contract, pagination and failed-run tests."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trakt_sync", ROOT / "scripts/trakt-sync/trakt_sync.py")
trakt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = trakt
spec.loader.exec_module(trakt)
USER = "00000000-0000-4000-8000-000000000001"


class Response:
    def __init__(self, data, page, pages, count):
        self.status = 200
        self.data = data
        self.headers = {"X-Pagination-Page": str(page),
                        "X-Pagination-Page-Count": str(pages),
                        "X-Pagination-Item-Count": str(count)}

    def read(self, *_):
        return json.dumps(self.data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.next_row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, args=()):
        self.statements.append((sql, args))
        if "select watermark" in sql:
            self.next_row = None
        elif "returning id" in sql:
            self.next_row = (UUID("00000000-0000-4000-8000-000000000002"),)

    def fetchone(self):
        return self.next_row


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()

    def transaction(self):
        return self

    def cursor(self):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class TraktTests(unittest.TestCase):
    def setUp(self):
        self.fixture = trakt.fixture_snapshot(ROOT / "fixtures/trakt")

    def test_sanitized_snapshot_and_rewatch_ids(self):
        self.assertEqual({k: len(v) for k, v in self.fixture.feeds.items()},
                         dict(history_movies=2, history_episodes=1, ratings_movies=1,
                              ratings_shows=1, watchlist_movies=1, watchlist_shows=1))
        first, second = self.fixture.feeds["history_movies"]
        self.assertNotEqual(trakt.identity("history_movies", first)[2],
                            trakt.identity("history_movies", second)[2])
        self.assertEqual(trakt.identity("history_movies", first)[1],
                         trakt.identity("history_movies", second)[1])

    def test_duplicate_or_malformed_feed_fails_before_database(self):
        bad = {k: list(v) for k, v in self.fixture.feeds.items()}
        bad["history_movies"].append(bad["history_movies"][0])
        with self.assertRaisesRegex(trakt.SourceError, "duplicate"):
            trakt.Snapshot(bad, self.fixture.fetched_at).validate()
        bad["history_movies"][-1] = dict(movie={"ids": {"trakt": 301}})
        with self.assertRaisesRegex(trakt.SourceError, "stable ID"):
            trakt.Snapshot(bad, self.fixture.fetched_at).validate()

    def test_pagination_includes_last_page_and_requires_complete_count(self):
        calls = []

        def opener(request, timeout):
            self.assertEqual(timeout, 30)
            calls.append(request.full_url)
            page = int(request.full_url.split("page=")[1].split("&")[0])
            return Response([{"id": page}], page, 2, 2)

        transport = trakt.TraktHTTP("client", "token", opener=opener, sleep=lambda _: None)
        batch, pages, count = transport.page("history_movies", 1, 100)
        self.assertEqual((len(batch), pages, count), (1, 2, 2))
        self.assertIn("/sync/history/movies?", calls[0])
        self.assertEqual(transport.page("history_movies", 2, 100)[0], [{"id": 2}])

    def test_complete_fetch_rejects_repeated_or_missing_pages(self):
        def opener(request, timeout):
            path = urlparse(request.full_url)
            feed = next(name for name, url in trakt.FEEDS.items() if url == path.path)
            page = int(parse_qs(path.query)["page"][0])
            items = self.fixture.feeds[feed]
            if feed == "history_movies":
                return Response(items[page - 1:page], page, 2, 2)
            return Response(items, page, 1, len(items))

        fetched = trakt.TraktHTTP("client", "token", opener=opener).fetch(limit=1)
        self.assertEqual(len(fetched.feeds["history_movies"]), 2)

        def repeated(request, timeout):
            path = urlparse(request.full_url)
            feed = next(name for name, url in trakt.FEEDS.items() if url == path.path)
            if feed == "history_movies":
                page = int(parse_qs(path.query)["page"][0])
                return Response([self.fixture.feeds[feed][0]], page, 2, 2)
            return Response(self.fixture.feeds[feed], 1, 1, 1)

        with self.assertRaisesRegex(trakt.SourceError, "duplicate"):
            trakt.TraktHTTP("client", "token", opener=repeated).fetch(limit=1)

        def missing(request, timeout):
            path = urlparse(request.full_url)
            feed = next(name for name, url in trakt.FEEDS.items() if url == path.path)
            if feed == "history_movies":
                page = int(parse_qs(path.query)["page"][0])
                return Response(self.fixture.feeds[feed][0:1] if page == 1 else [], page, 2, 2)
            return Response(self.fixture.feeds[feed], 1, 1, 1)

        with self.assertRaisesRegex(trakt.SourceError, "truncated page"):
            trakt.TraktHTTP("client", "token", opener=missing).fetch(limit=1)

    def test_rate_limit_retries_and_auth_failure_does_not_retry(self):
        calls, delays = [], []

        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 429, "rate limit", {"Retry-After": "2"}, None)
            return Response([], 1, 0, 0)

        transport = trakt.TraktHTTP("client", "token", opener=opener, sleep=delays.append)
        self.assertEqual(transport.page("history_movies", 1, 100), ([], 0, 0))
        self.assertEqual(len(delays), 1)
        self.assertGreaterEqual(delays[0], 2)

        def unauthorized(request, timeout):
            raise HTTPError(request.full_url, 401, "expired", {}, None)

        with self.assertRaisesRegex(trakt.SourceError, "HTTP 401"):
            trakt.TraktHTTP("client", "expired", opener=unauthorized).page("history_movies", 1, 100)

    def test_fetch_failure_records_failed_run_without_checkpoint(self):
        conn = FakeConnection()

        def broken_fetch():
            raise trakt.SourceError("partial pagination")

        with self.assertRaises(trakt.SourceError):
            trakt.run(conn, broken_fetch, USER, set())
        sql = "\n".join(query for query, _ in conn.cur.statements)
        self.assertIn("insert into public.marquee_sync_runs", sql)
        self.assertIn("status='failed'", sql)
        self.assertIn("last_error", sql)
        self.assertNotIn("last_success_run_id=excluded.last_success_run_id", sql)


if __name__ == "__main__":
    unittest.main()
