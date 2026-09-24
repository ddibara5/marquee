"""Fabricated candidate numbers and AniList response; no private history."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from anilist_episode_evidence import ReviewError, anilist_metadata, evidence


def event(season, number, air_date):
    return {"panel": {"episode_metadata": {
        "season_id": season, "episode_number": number,
        "episode_air_date": air_date}}}


class AniListEvidenceTests(unittest.TestCase):
    def test_one_public_batch_uses_ids_without_logging_private_data(self):
        def requester(request):
            variables = json.loads(request.data)["variables"]
            self.assertEqual(variables["ids"], [101, 202])
            return {"data": {"Page": {"pageInfo": {"hasNextPage": False},
                                     "media": [{"id": 101, "episodes": 12,
                                                "startDate": {"year": 2025}},
                                               {"id": 202, "episodes": None,
                                                "startDate": {"year": 2026}}]}}}

        self.assertEqual(anilist_metadata({"202", "101"}, requester=requester),
                         {101: (12, 2025), 202: (None, 2026)})
        with self.assertRaises(ReviewError):
            anilist_metadata({"101"}, requester=lambda _: {
                "data": {"Page": {"pageInfo": {"hasNextPage": False}, "media": []}}})

    def test_number_and_year_are_review_clues_never_approved_mappings(self):
        rows = {"a": {"candidates": [{"anilist_media_id": "101"}]},
                "b": {"candidates": [{"anilist_media_id": "202"}]},
                "c": {"candidates": []}}
        records = [event("a", 3, "2025-04-01"), event("a", 12, "2025-06-01"),
                   event("b", 14, "2020-01-01"), event("c", 1, "2026-01-01")]
        out = evidence(records, rows, {101: (12, 2025), 202: (10, 2026)})
        self.assertEqual(out["one_title_candidate_seasons"], 2)
        self.assertEqual(out["observed_numbers_within_anilist_total"], 1)
        self.assertEqual(out["highest_observed_equals_anilist_total"], 1)
        self.assertEqual(out["observed_number_exceeds_anilist_total"], 1)
        self.assertEqual(out["year_and_number_both_compatible"], 1)
        self.assertNotIn("approved_mappings", out)


if __name__ == "__main__":
    unittest.main()
