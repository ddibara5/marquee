"""Offline safety and candidate contract tests for the Crunchyroll/AniList comparison."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/crunchyroll"
sys.path.insert(0, str(SCRIPT))
spec = importlib.util.spec_from_file_location("catalog_overlap_probe", SCRIPT / "catalog_overlap_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CatalogOverlapTests(unittest.TestCase):
    def test_title_candidates_never_emit_ids_or_titles(self):
        seasons = [("private-target-1", "Fabricated Show", "Fabricated Season"),
                   ("private-target-2", "Fabricated Show", "Other Season")]
        pages = [[{"id": "private-event", "panel": {"id": "private-episode",
                    "episode_metadata": {"series_id": "private-series", "season_id": "private-season",
                                         "series_title": "fabricated show",
                                         "season_title": "Fabricated Season"}}},
                  {"id": "private-event-2", "parent_id": "private-series"},
                  {"id": "private-event-3", "panel": {"id": "private-movie", "type": "movie",
                        "title": "Fabricated Film"}}]]
        result = probe.compare(pages, seasons, [("private-film", "Fabricated Film")])
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["without_episode_metadata"], 2)
        self.assertEqual(result["movie_title_candidates"], {"one": 1, "multiple": 0, "none": 0})
        self.assertEqual(result["candidate_counts"]["one_title_candidate"],
                         {"source_seasons": 1, "observations": 1})
        rendered = json.dumps(result)
        self.assertNotIn("private-", rendered)
        self.assertNotIn("Fabricated", rendered)

    def test_series_only_match_is_ambiguous_and_conflict_is_flagged(self):
        seasons = [("a", "Same Show", "Season A"), ("b", "Same Show", "Season B"),
                   ("c", "Different Show", "Wrong Season")]
        pages = [[{"panel": {"id": "ep1", "episode_metadata": {
            "series_id": "show", "season_id": "one", "series_title": "Same Show"}}},
                  {"panel": {"id": "ep2", "episode_metadata": {
            "series_id": "show", "season_id": "two", "series_title": "Same Show",
            "season_title": "Wrong Season"}}}]]
        result = probe.compare(pages, seasons, [])
        self.assertEqual(result["candidate_counts"]["multiple_title_candidates"]["source_seasons"], 1)
        self.assertEqual(result["candidate_counts"]["conflicting_title_evidence"]["source_seasons"], 1)


if __name__ == "__main__":
    unittest.main()
