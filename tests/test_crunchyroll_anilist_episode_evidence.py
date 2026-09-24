"""Fabricated candidate numbers and AniList response; no private history."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from anilist_episode_evidence import (ReviewError, anilist_metadata,
                                      crunchyroll_series_id, evidence, series_proposals)


def event(season, number, air_date):
    return {"panel": {"episode_metadata": {
        "season_id": season, "series_id": "series-1", "episode_number": number,
        "episode_air_date": air_date}}}


class AniListEvidenceTests(unittest.TestCase):
    def test_one_public_batch_uses_ids_without_logging_private_data(self):
        def requester(request):
            variables = json.loads(request.data)["variables"]
            self.assertEqual(variables["ids"], [101, 202])
            return {"data": {"Page": {"pageInfo": {"hasNextPage": False},
                                     "media": [{"id": 101, "episodes": 12,
                                                "startDate": {"year": 2025},
                                                "externalLinks": [{"site": "Crunchyroll",
                                                  "url": "https://www.crunchyroll.com/series/series-1/example"}]},
                                               {"id": 202, "episodes": None,
                                                "startDate": {"year": 2026},
                                                "externalLinks": []}]}}}

        self.assertEqual(anilist_metadata({"202", "101"}, requester=requester),
                         {101: (12, 2025, {"series-1"}), 202: (None, 2026, set())})
        with self.assertRaises(ReviewError):
            anilist_metadata({"101"}, requester=lambda _: {
                "data": {"Page": {"pageInfo": {"hasNextPage": False}, "media": []}}})

    def test_number_and_year_are_review_clues_never_approved_mappings(self):
        rows = {"a": {"candidates": [{"anilist_media_id": "101"}]},
                "b": {"candidates": [{"anilist_media_id": "202"}]},
                "c": {"candidates": []}}
        records = [event("a", 3, "2025-04-01"), event("a", 12, "2025-06-01"),
                   event("b", 14, "2020-01-01"), event("c", 1, "2026-01-01")]
        out = evidence(records, rows, {101: (12, 2025, {"series-1"}),
                                       202: (10, 2026, {"other-series"})})
        self.assertEqual(out["one_title_candidate_seasons"], 2)
        self.assertEqual(out["observed_numbers_within_anilist_total"], 1)
        self.assertEqual(out["highest_observed_equals_anilist_total"], 1)
        self.assertEqual(out["observed_number_exceeds_anilist_total"], 1)
        self.assertEqual(out["year_and_number_both_compatible"], 1)
        self.assertEqual(out["exact_source_series_id_in_anilist_link"], 1)
        self.assertEqual(out["distinct_exact_linked_source_series"], 1)
        self.assertEqual(out["distinct_exact_linked_anilist_media"], 1)
        self.assertEqual(out["exact_link_with_compatible_year_and_number"], 1)
        self.assertEqual(out["anilist_link_points_to_other_series"], 1)
        self.assertNotIn("approved_mappings", out)

    def test_series_url_parser_requires_exact_host_and_series_path(self):
        self.assertEqual(crunchyroll_series_id(
            "https://www.crunchyroll.com/en-us/series/SOURCE1/show"), "SOURCE1")
        self.assertIsNone(crunchyroll_series_id(
            "https://www.crunchyroll.com.evil.example/series/SOURCE1"))
        self.assertIsNone(crunchyroll_series_id(
            "https://www.crunchyroll.com/watch/SOURCE1"))

    def test_shared_series_requires_consistent_canonical_show(self):
        rows = {"a": {"candidates": [{"anilist_media_id": "101",
                                       "canonical_season_id": "season-1"}]},
                "b": {"candidates": [{"anilist_media_id": "202",
                                       "canonical_season_id": "season-2"}]}}
        records = [event("a", 1, "2025-01-01"), event("b", 1, "2026-01-01")]
        metadata = {101: (12, 2025, {"series-1"}),
                    202: (12, 2026, {"series-1"})}
        same = evidence(records, rows, metadata,
                        {"season-1": "show-1", "season-2": "show-1"})
        self.assertEqual(same["distinct_exact_linked_source_series"], 1)
        self.assertEqual(same["exact_linked_series_with_multiple_anilist_media"], 1)
        self.assertEqual(same["exact_linked_series_with_one_canonical_show"], 1)
        conflict = evidence(records, rows, metadata,
                            {"season-1": "show-1", "season-2": "show-2"})
        self.assertEqual(conflict["exact_linked_series_with_conflicting_canonical_shows"], 1)

    def test_proposal_excludes_candidate_conflicts_and_parent_disagreements(self):
        rows = {"a": {"candidates": [{"anilist_media_id": "101",
                                       "canonical_season_id": "season-1"}]},
                "b": {"candidates": [{"anilist_media_id": "202",
                                       "canonical_season_id": "season-2"}]}}
        records = [event("a", 1, "2025-01-01"), event("b", 2, "2025-02-01")]
        for record in records:
            record["parent_id"] = "series-1"
        metadata = {101: (12, 2025, {"series-1"}),
                    202: (12, 2025, set())}
        targets = {"season-1": "show-1", "season-2": "show-1"}
        safe, counts = series_proposals(records, rows, metadata, targets)
        self.assertEqual(safe, {"series-1": "show-1"})
        self.assertEqual(counts["series_with_unambiguous_show_target"], 1)
        targets["season-2"] = "show-2"
        safe, counts = series_proposals(records, rows, metadata, targets)
        self.assertEqual(safe, {})
        self.assertEqual(counts["excluded_conflicting_show_candidates"], 1)
        targets["season-2"] = "show-1"
        records[1]["parent_id"] = "different-series"
        safe, counts = series_proposals(records, rows, metadata, targets)
        self.assertEqual(safe, {})
        self.assertEqual(counts["excluded_parent_series_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
