import copy
import importlib.util
from io import BytesIO
import json
from pathlib import Path
from unittest import TestCase, main
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("anilist_import", ROOT / "scripts/anilist-import/anilist_import.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
SAMPLE = json.loads((ROOT / "fixtures/anilist/list.json").read_text())


class ListContractTests(TestCase):
    def test_full_list_deduplicates_custom_lists_and_preserves_scores(self):
        snapshot = adapter.validate(SAMPLE, "ExampleAccount")
        self.assertEqual(len(snapshot["entries"]), 2)
        self.assertEqual(snapshot["entries"][0]["score"], 85)
        self.assertEqual(adapter.parse_score(snapshot["entries"][0]["score10"]), 8.5)
        self.assertEqual(adapter.anime_relations(snapshot["entries"][1]["media"]), [("2003", "PREQUEL")])

    def test_graphql_errors_or_missing_groups_fail_loudly(self):
        with self.assertRaises(adapter.SourceError):
            adapter.validate({"data": SAMPLE["data"], "errors": [{"message": "unauthorized"}]}, "ExampleAccount")
        bad = copy.deepcopy(SAMPLE)
        del bad["data"]["MediaListCollection"]["lists"]
        with self.assertRaises(adapter.SourceError):
            adapter.validate(bad, "ExampleAccount")

    def test_conflicting_duplicate_or_wrong_owner_fails(self):
        bad = copy.deepcopy(SAMPLE)
        bad["data"]["MediaListCollection"]["lists"][1]["entries"][0]["status"] = "DROPPED"
        with self.assertRaises(adapter.SourceError):
            adapter.validate(bad, "ExampleAccount")
        bad = copy.deepcopy(SAMPLE)
        bad["data"]["MediaListCollection"]["lists"][0]["entries"][0]["userId"] = 999
        with self.assertRaises(adapter.SourceError):
            adapter.validate(bad, "ExampleAccount")

    def test_unrated_and_status_mapping(self):
        self.assertEqual(adapter.parse_score(None), 0)
        self.assertEqual(adapter.STATUSES["REPEATING"], "watching")
        with self.assertRaises(adapter.SourceError):
            adapter.parse_score(8.33)

    def test_rate_limit_retry_and_complete_response_validation(self):
        attempts = []
        delays = []

        def opener(request, timeout):
            attempts.append(request)
            if len(attempts) == 1:
                raise HTTPError(adapter.API_URL, 429, "rate limited", {"Retry-After": "0"}, None)
            return BytesIO(json.dumps(SAMPLE).encode())

        snapshot = adapter.fetch("ExampleAccount", opener=opener, sleep=delays.append)
        self.assertEqual(len(snapshot["entries"]), 2)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(delays), 1)

    def test_empty_or_wrong_account_never_claims_success(self):
        with self.assertRaises(adapter.SourceError):
            adapter.validate(SAMPLE, "OtherAccount")
        bad = copy.deepcopy(SAMPLE)
        bad["data"]["MediaListCollection"]["lists"] = []
        with self.assertRaises(adapter.SourceError):
            adapter.validate(bad, "ExampleAccount")


class Cursor:
    def __init__(self, mapping=None):
        self.mapping = mapping
        self.statements = []
        self.rowcount = 1
        self.last = None

    def execute(self, sql, args):
        self.statements.append(sql)
        if "from public.marquee_source_mappings" in sql:
            self.last = self.mapping
        elif "insert into public.marquee_titles" in sql:
            self.last = ("title-uuid",)
        elif "insert into public.marquee_seasons" in sql:
            self.last = ("season-uuid",)
        elif "from public.marquee_seasons" in sql:
            self.last = (True,)

    def fetchone(self):
        return self.last


class MappingSafetyTests(TestCase):
    def test_related_anime_goes_to_review_before_catalog_writes(self):
        entry = SAMPLE["data"]["MediaListCollection"]["lists"][0]["entries"][1]
        cursor = Cursor()
        with self.assertRaises(adapter.Review):
            adapter.resolve(cursor, entry)
        self.assertFalse(any("insert into public.marquee_titles" in sql for sql in cursor.statements))

    def test_standalone_creates_stable_id_mapping(self):
        entry = SAMPLE["data"]["MediaListCollection"]["lists"][0]["entries"][0]
        cursor = Cursor()
        self.assertEqual(adapter.resolve(cursor, entry), ("season_id", "season-uuid"))
        self.assertTrue(any("standalone-no-anime-relations-v1" in sql for sql in cursor.statements))

    def test_standalone_film_is_a_movie(self):
        entry = copy.deepcopy(SAMPLE["data"]["MediaListCollection"]["lists"][0]["entries"][0])
        entry["media"]["format"] = "MOVIE"
        cursor = Cursor()
        self.assertEqual(adapter.resolve(cursor, entry), ("title_id", "title-uuid"))
        self.assertTrue(any("insert into public.marquee_movies" in sql for sql in cursor.statements))
        self.assertFalse(any("insert into public.marquee_seasons" in sql for sql in cursor.statements))


if __name__ == "__main__":
    main()
