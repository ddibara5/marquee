"""Fabricated full-feed failure modes for the read-only import gate."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from history_probe import ProbeError
from import_gate import inspect


def item(event, panel="panel-a", number=1):
    return {"id": event, "date_played": "2026-09-23T01:02:03Z",
            "panel": {"id": panel, "episode_metadata": {
                "series_id": "series-a", "season_id": "season-a", "episode_number": number}}}


class ImportGateTests(unittest.TestCase):
    def test_repeated_episode_is_distinct_event_but_never_auto_imported(self):
        result = inspect([[item("event-1"), item("event-2")],
                          [dict(id="event-3", date_played="2026-09-23T01:02:03Z")]], minimum=3)
        self.assertEqual((result["events"], result["unique_panel_ids_with_identity"],
                          result["repeat_panel_observations"], result["without_panel_id"]), (3, 1, 1, 1))
        self.assertEqual(result["importable_without_review"], 0)

    def test_duplicate_event_and_conflicting_panel_are_fatal(self):
        for pages in ([[item("event-1"), item("event-1")]],
                      [[item("event-1"), item("event-2", number=2)]]):
            with self.subTest(pages=pages), self.assertRaises(ProbeError):
                inspect(pages, minimum=2)

    def test_incomplete_iterator_or_missing_date_never_passes(self):
        def broken():
            yield [item("event-1")]
            raise ProbeError("Legacy pagination link is invalid or repeated")
        with self.assertRaises(ProbeError):
            inspect(broken(), minimum=1)
        with self.assertRaises(ProbeError):
            inspect([[item("event-1")]], minimum=2)
        with self.assertRaises(ProbeError):
            inspect([[dict(id="event-1")]], minimum=1)

    def test_newer_events_cannot_hide_lost_oldest_coverage(self):
        with self.assertRaises(ProbeError):
            inspect(([item(f"event-{i}")] for i in range(7933)))


if __name__ == "__main__":
    unittest.main()
