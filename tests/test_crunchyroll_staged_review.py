"""Invented version, catalog, and timestamp evidence; no private history."""

from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from staged_review import ReviewError, analyze


def event(event_id, panel_id, season_id, locale, at="2026-09-23T01:02:03Z", watched=True):
    return {"id": event_id, "date_played": at, "parent_id": "parent-a",
            "fully_watched": watched, "panel": {"id": panel_id, "episode_metadata": {
                "identifier": "one-source-episode", "series_id": "series-a",
                "season_id": season_id, "episode_number": 1,
                "series_title": "English series", "season_title": "English series",
                "audio_locale": locale,
                "versions": [{"guid": "panel-a", "season_guid": "season-a"},
                             {"guid": "panel-b", "season_guid": "season-b"}]}}}


SEASONS = [("canonical-season", "Romaji series", "Romaji series",
            ["English series"], "123", [{"node": {"id": 456}}])]


class StagedReviewTests(unittest.TestCase):
    def test_same_time_versions_are_one_candidate_time_group_not_two_watches(self):
        rows = [event("one", "panel-a", "season-a", "ja-JP"),
                event("two", "panel-b", "season-b", "en-US")]
        result = analyze(rows, SEASONS)
        self.assertEqual(result["raw_events"], 2)
        self.assertEqual(result["source_episode_version_groups"], 1)
        self.assertEqual(result["source_episode_time_groups"], 1)
        self.assertEqual(result["same_time_extra_observations"], 1)
        self.assertEqual(result["version_group_title_evidence"], {"consistent_one_title_candidate": 1})
        self.assertEqual(result["approved_crunchyroll_episode_mappings"], 0)
        self.assertEqual(result["timestamp_overlap"], {})
        self.assertNotIn("panel-a", str(result))

    def test_rewatch_partial_and_approved_trakt_pair_stay_separate(self):
        later = event("later", "panel-a", "season-a", "ja-JP",
                      "2026-09-25T01:02:03Z", watched=False)
        rows = [event("one", "panel-a", "season-a", "ja-JP"), later]
        trakt = [("canonical-episode", datetime(2026, 9, 23, 1, 4, tzinfo=timezone.utc))]
        result = analyze(rows, SEASONS, {"panel-a": "canonical-episode"}, trakt)
        self.assertEqual(result["source_episode_time_groups"], 2)
        self.assertEqual(result["partial_groups"], 1)
        self.assertEqual(result["timestamp_overlap"]["within_5_minutes"], 1)
        self.assertEqual(result["timestamp_overlap"]["more_than_24_hours"], 1)

    def test_missing_panel_and_conflicting_source_are_review_not_guess(self):
        missing = {"id": "missing", "date_played": "2026-09-23T01:02:03Z"}
        result = analyze([missing, event("one", "panel-a", "season-a", "ja-JP")], SEASONS)
        self.assertEqual(result["without_panel"], 1)
        conflicting = event("two", "panel-b", "season-b", "en-US")
        conflicting["panel"]["episode_metadata"]["series_id"] = "another-series"
        with self.assertRaises(ReviewError):
            analyze([event("one", "panel-a", "season-a", "ja-JP"), conflicting], SEASONS)

    def test_same_time_conflict_and_duplicate_event_fail_closed(self):
        first = event("one", "panel-a", "season-a", "ja-JP")
        second = event("two", "panel-b", "season-b", "en-US", watched=False)
        with self.assertRaises(ReviewError):
            analyze([first, second], SEASONS)
        with self.assertRaises(ReviewError):
            analyze([first, first], SEASONS)


if __name__ == "__main__":
    unittest.main()
