"""Invented CMS identities; no source history or secrets."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/crunchyroll"))
from history_probe import ProbeError
from parent_catalog_probe import lookup_series, summarize


class ParentCatalogTests(unittest.TestCase):
    def test_verified_series_and_unknown_parent_aggregate_without_ids(self):
        def requester(request):
            series_id = request.full_url.split("/series/")[1].split("?")[0]
            return {"data": [{"id": series_id, "title": "private title"}]}

        result = summarize({"SERIES1": 4, "SERIES2": 1}, {"SERIES1"},
                           "invented-token", requester=requester)
        self.assertEqual(result["catalog_verified_parents"], 2)
        self.assertEqual(result["unseen_parent_catalog_verified"], 1)
        self.assertEqual(result["events_with_known_parent_series"], 4)
        self.assertNotIn("SERIES", str(result))
        self.assertNotIn("private title", str(result))

    def test_absent_or_mismatched_series_is_not_a_match(self):
        def absent(_):
            raise ProbeError("Crunchyroll request failed (HTTP 404)")

        self.assertEqual(lookup_series("SERIES1", "invented-token", requester=absent),
                         "not_found")
        with self.assertRaises(ProbeError):
            lookup_series("SERIES1", "invented-token",
                          requester=lambda _: {"data": [{"id": "OTHER"}]})
        with self.assertRaises(ProbeError):
            lookup_series("bad/series", "invented-token",
                          requester=lambda _: {"data": []})


if __name__ == "__main__":
    unittest.main()
