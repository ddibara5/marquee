"""Invented version and catalog evidence; no private history."""

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
    def test_same_time_versions_do_not_prove_a_single_watch(self):
        rows = [event("one", "panel-a", "season-a", "ja-JP"),
                event("two", "panel-b", "season-b", "en-US")]
        result = analyze(rows, SEASONS)
        self.assertEqual(result["raw_events"], 2)
        self.assertEqual(result["source_episode_version_groups"], 1)
        self.assertEqual(result["completed_source_episode_groups"], 1)
        self.assertEqual(result["distinct_source_timestamps"], 1)
        self.assertEqual(result["version_group_title_evidence"], {"consistent_one_title_candidate": 1})
        self.assertEqual(result["approved_crunchyroll_episode_mappings"], 0)
        self.assertEqual(result["identity_overlap"], {})
        self.assertNotIn("panel-a", str(result))

    def test_trakt_overlap_uses_episode_identity_never_source_time(self):
        later = event("later", "panel-a", "season-a", "ja-JP",
                      "2026-09-25T01:02:03Z", watched=False)
        rows = [event("one", "panel-a", "season-a", "ja-JP"), later]
        trakt = ({"canonical-episode"}, 1)
        result = analyze(rows, SEASONS, {"panel-a": "canonical-episode"}, trakt)
        self.assertEqual(result["completed_source_episode_groups"], 1)
        self.assertEqual(result["identity_overlap"], {
            "approved_crunchyroll_episode_groups": 1,
            "same_canonical_episode_has_trakt_watches": 1})
        self.assertNotIn("timestamp_overlap", result)

    def test_partial_only_and_known_parent_are_counted_without_a_watch(self):
        one = event("one", "panel-a", "season-a", "ja-JP", watched=False)
        one["parent_id"] = "series-a"
        missing = {"id": "missing", "date_played": "2026-09-23T01:02:03Z",
                   "parent_id": "series-a"}
        result = analyze([one, missing], SEASONS)
        self.assertEqual(result["partial_only_source_episode_groups"], 1)
        self.assertEqual(result["completed_source_episode_groups"], 0)
        self.assertEqual(result["missing_panel_events_with_known_series"], 1)
        self.assertEqual(result["parent_matches_series"], 1)

    def test_missing_panel_and_conflicting_source_are_review_not_guess(self):
        missing = {"id": "missing", "date_played": "2026-09-23T01:02:03Z"}
        result = analyze([missing, event("one", "panel-a", "season-a", "ja-JP")], SEASONS)
        self.assertEqual(result["without_panel"], 1)
        conflicting = event("two", "panel-b", "season-b", "en-US")
        conflicting["panel"]["episode_metadata"]["series_id"] = "another-series"
        with self.assertRaises(ReviewError):
            analyze([event("one", "panel-a", "season-a", "ja-JP"), conflicting], SEASONS)

    def test_same_time_completion_disagreement_does_not_infer_a_watched_event(self):
        first = event("one", "panel-a", "season-a", "ja-JP")
        second = event("two", "panel-b", "season-b", "en-US", watched=False)
        result = analyze([first, second], SEASONS)
        self.assertEqual(result["completed_source_episode_groups"], 1)
        self.assertEqual(result["distinct_source_timestamps"], 1)
        with self.assertRaises(ReviewError):
            analyze([first, first], SEASONS)


if __name__ == "__main__":
    unittest.main()
