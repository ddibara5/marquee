"""Fabricated identity and version observations, never a live history fixture."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/crunchyroll"
sys.path.insert(0, str(SCRIPT))
spec = importlib.util.spec_from_file_location("identity_review_probe", SCRIPT / "identity_review_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class IdentityReviewTests(unittest.TestCase):
    def test_collision_and_identifier_counts_do_not_emit_records(self):
        def item(panel_id, number, locale):
            return {"id": "private-event-" + panel_id, "panel": {"id": panel_id,
                "episode_metadata": {"series_id": "private-series", "season_id": "private-season",
                                     "episode_number": number, "identifier": "private-identifier",
                                     "audio_locale": locale}}}
        result = probe.identity_review([[item("private-episode-a", "1", "en-US"),
                                         item("private-episode-b", 1, "ja-JP"),
                                         {"id": "private-unavailable"}]])
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["no_episode_metadata"], 1)
        self.assertEqual(result["season_episode_numbers_with_multiple_panel_ids"], 1)
        self.assertEqual(result["identifiers_shared_by_multiple_panel_ids"], 1)
        self.assertEqual(result["season_episode_numbers_with_multiple_audio_locales"], 1)
        self.assertNotIn("private-", json.dumps(result))

    def test_one_anilist_candidate_does_not_resolve_number_collision(self):
        pages = [[{"panel": {"id": panel, "episode_metadata": {
            "series_id": "series", "season_id": "season", "series_title": "English Show",
            "episode_number": 1}}} for panel in ("version-a", "version-b")]]
        seasons = [("canonical-season", "Romaji Show", "Romaji Show", ["English Show"])]
        result = probe.identity_review(pages, seasons)
        self.assertEqual(result["one_title_candidate_source_seasons"], 1)
        self.assertEqual(result["one_candidate_with_episode_number_collision"], 1)


if __name__ == "__main__":
    unittest.main()
