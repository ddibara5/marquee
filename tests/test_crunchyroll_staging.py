"""Fabricated source identity and atomic replay behavior for raw-only staging."""

from contextlib import contextmanager
from copy import deepcopy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from stage_history import StageError, observations, stage


USER = "c566e7e0-880a-430d-85df-c40484144a91"


def observation(event, panel="panel-a", number=1):
    return {"id": event, "date_played": "2026-09-23T01:02:03Z", "panel": {
        "id": panel, "episode_metadata": {"series_id": "series-a", "season_id": "season-a",
                                 "episode_number": number}}}


class MemoryCursor:
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
        if "select watermark->>'account_digest'" in sql:
            self.result = (self.store.get("account_digest"),) if self.store.get("account_digest") else None
        elif "select dedupe_key" in sql:
            self.result = [(key,) for key in self.store["events"]]
        elif "select count(*) from public.marquee_source_mappings" in sql:
            self.result = (0,)
        elif "select count(*) from public.marquee_watch_history_sources" in sql:
            self.result = (0,)
        elif "select payload->>'date_played'" in sql:
            item = self.store["events"].get(args[1])
            self.result = (item["date_played"], item.get("panel", {}).get("id")) if item else None
        elif "insert into public.marquee_sync_runs" in sql:
            self.result = ("fake-run",)
        elif "insert into public.marquee_ingest_raw" in sql:
            import json
            self.store["events"][args[3]] = json.loads(args[5])
            self.rowcount = 1
        elif "insert into public.marquee_mapping_review" in sql:
            key = args[:2]
            self.rowcount = int(key not in self.store["reviews"])
            self.store["reviews"].add(key)
        elif "update public.marquee_sync_runs" in sql:
            self.rowcount = 1
        elif "insert into public.marquee_sync_state" in sql:
            import json
            self.store["account_digest"] = json.loads(args[2])["account_digest"]
            self.rowcount = 1
        else:
            raise AssertionError("Unexpected SQL in raw-only stage")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class MemoryConnection:
    def __init__(self):
        self.store = {"events": {}, "reviews": set()}

    @contextmanager
    def transaction(self):
        before = deepcopy(self.store)
        try:
            yield
        except Exception:
            self.store = before
            raise

    def cursor(self):
        return MemoryCursor(self.store)


class StageTests(unittest.TestCase):
    def test_missing_panel_and_number_remain_reviewable(self):
        result = list(observations([[observation("one", number=None),
                                     {"id": "two", "date_played": "2026-09-23T01:02:03Z"}]]))
        self.assertEqual([len(reviews) for _, reviews in result], [2, 1])
        self.assertEqual(result[1][1][0][0], "history_event")

    def test_atomic_replay_and_changed_event_rejection(self):
        conn = MemoryConnection()
        first = stage(conn, USER, [[observation("one"), observation("two")]], "account-a")
        self.assertEqual((first["events_inserted"], first["canonical_watches_created"]), (2, 0))
        replay = stage(conn, USER, [[observation("one"), observation("two")]], "account-a")
        self.assertEqual((replay["events_inserted"], replay["events_replayed"],
                          replay["new_review_groups"]), (0, 2, 0))
        with self.assertRaises(StageError):
            stage(conn, USER, [[observation("one", panel="different"),
                                observation("two")]], "account-a")
        self.assertEqual(conn.store["events"]["one"]["panel"]["id"], "panel-a")
        with self.assertRaises(StageError):
            stage(conn, USER, [[observation("two")]], "account-a")
        self.assertEqual(len(conn.store["events"]), 2)
        with self.assertRaises(StageError):
            stage(conn, USER, [[observation("one"), observation("two")]], "account-b")


if __name__ == "__main__":
    unittest.main()
