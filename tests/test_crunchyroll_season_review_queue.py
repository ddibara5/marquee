"""Fabricated candidates and transaction guards; never live history."""

from contextlib import contextmanager
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from season_review_queue import ReviewError, apply_review, prepare


def sample(season, show_title="Shared title", season_title="Shared title"):
    return {"id": "event-" + season, "panel": {"id": "panel-" + season,
            "episode_metadata": {"series_id": "series", "season_id": season,
                                 "series_title": show_title, "season_title": season_title}}}


class ReviewQueueTests(unittest.TestCase):
    def test_unique_title_stays_review_only_and_relation_marks_ambiguity(self):
        seasons = [("target-1", "Shared title", "Shared title", [], "101",
                    [{"node": {"id": 202}}]),
                   ("target-2", "Other title", "Other title", [], "202", [])]
        rows, counts = prepare([sample("s1"), sample("s2", "Other title", "Other title")], seasons)
        self.assertEqual(counts, {"one": 2})
        self.assertEqual(len(rows["s1"]["candidates"]), 1)
        self.assertTrue(rows["s1"]["candidates"][0]["review_only"])
        ambiguous, categories = prepare([sample("s3", "Other title", "Shared title")], seasons)
        self.assertEqual(categories, {"conflicting": 1})
        self.assertTrue(all(c["relation_to_another_candidate"] for c in ambiguous["s3"]["candidates"]))

    def test_reused_source_season_across_series_fails(self):
        other = sample("s1")
        other["panel"]["episode_metadata"]["series_id"] = "other-series"
        with self.assertRaises(ReviewError):
            prepare([sample("s1"), other], [])


class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.result = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, args=()):
        self.rowcount = 0
        if "pg_advisory_xact_lock" in sql:
            return
        if "select watermark->>" in sql:
            self.result = (str(len(self.store["events"])),)
        elif "select dedupe_key" in sql:
            self.result = [(key,) for key in self.store["events"]]
        elif "select count(*) from public.marquee_source_mappings" in sql:
            self.result = (self.store["mappings"],)
        elif "select source_id from public.marquee_mapping_review" in sql:
            self.result = [(key,) for key in self.store["reviews"]]
        elif "update public.marquee_mapping_review" in sql:
            self.store["reviews"][args[3]] = args[0]
            self.rowcount = 1
        else:
            raise AssertionError("Unexpected SQL in review-only update")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class FakeConnection:
    def __init__(self):
        self.store = {"events": {"event-a"}, "mappings": 0, "reviews": {"season-a": "[]"}}

    @contextmanager
    def transaction(self):
        before = deepcopy(self.store)
        try:
            yield
        except Exception:
            self.store = before
            raise

    def cursor(self):
        return FakeCursor(self.store)


class ApplyReviewTests(unittest.TestCase):
    def test_apply_only_updates_existing_review_and_replay_is_stable(self):
        conn = FakeConnection()
        row = {"season-a": {"candidates": [], "reason": "needs review", "source_title": "invented"}}
        self.assertEqual(apply_review(conn, "user-id", row, {"event-a"}), 1)
        first = deepcopy(conn.store)
        self.assertEqual(apply_review(conn, "user-id", row, {"event-a"}), 1)
        self.assertEqual(conn.store, first)
        with self.assertRaises(ReviewError):
            apply_review(conn, "user-id", row, {"different-event"})
        self.assertEqual(conn.store, first)
        conn.store["mappings"] = 1
        with self.assertRaises(ReviewError):
            apply_review(conn, "user-id", row, {"event-a"})


if __name__ == "__main__":
    unittest.main()
