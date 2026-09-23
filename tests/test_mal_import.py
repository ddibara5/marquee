import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mal_import", ROOT / "scripts/mal-import/mal_import.py")
mal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mal)


class ExportTests(unittest.TestCase):
    def test_fixture_status_score_and_provenance(self):
        rows, digest = mal.load_export(ROOT / "fixtures/mal/list.xml")
        self.assertEqual(len(digest), 64)
        self.assertEqual([(x["mal_id"], x["status"], x["score"]) for x in rows],
                         [("12345", "completed", 8), ("67890", "planned", 0)])
        self.assertEqual(rows[0]["payload"]["series_title"], "Example Orbit")
        self.assertIsNone(rows[1]["updated_at"])

    def test_reject_duplicates_unknown_status_and_entities(self):
        sample = (ROOT / "fixtures/mal/list.xml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "list.xml"
            for edited in (sample.replace("67890", "12345"),
                           sample.replace("Plan to Watch", "Unrecognized"),
                           sample.replace("<myanimelist>", "<!DOCTYPE x [<!ENTITY y 'z'>]><myanimelist>")):
                path.write_text(edited)
                with self.assertRaises(mal.ImportErrorMAL):
                    mal.load_export(path)


class FakeCursor:
    def __init__(self, status_exists=False, rating_exists=False, mapping=None, anime=True):
        self.existing = {"statuses": status_exists, "ratings": rating_exists}
        self.mapping = mapping
        self.anime = anime
        self.rowcount = 0
        self.last = None

    def execute(self, sql, args):
        if "from public.marquee_source_mappings" in sql:
            self.last = self.mapping
        elif "from public.marquee_seasons" in sql:
            self.last = (self.anime,)
        elif "from public.marquee_titles" in sql:
            self.last = ("show", self.anime)
        elif "insert into public.marquee_statuses" in sql or "insert into public.marquee_ratings" in sql:
            table = "statuses" if "marquee_statuses" in sql else "ratings"
            self.rowcount = 0 if self.existing[table] else 1
            self.existing[table] = True
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.last


class SeedTests(unittest.TestCase):
    def test_existing_status_and_rating_never_overwritten_on_replay(self):
        entry = mal.load_export(ROOT / "fixtures/mal/list.xml")[0][0]
        cur = FakeCursor(status_exists=True, rating_exists=True)
        self.assertEqual(mal.seed(cur, "owner", entry, "season_id", "season"),
                         {"inserted": 0, "skipped": 2})
        fresh = FakeCursor()
        self.assertEqual(mal.seed(fresh, "owner", entry, "season_id", "season"),
                         {"inserted": 2, "skipped": 0})
        self.assertEqual(mal.seed(fresh, "owner", entry, "season_id", "season"),
                         {"inserted": 0, "skipped": 2})

    def test_zero_score_does_not_insert_rating(self):
        entry = mal.load_export(ROOT / "fixtures/mal/list.xml")[0][1]
        self.assertEqual(mal.seed(FakeCursor(), "owner", entry, "season_id", "season"),
                         {"inserted": 1, "skipped": 0})

    def test_stable_mapping_required_and_non_anime_rejected(self):
        self.assertIsNone(mal.target(FakeCursor(), "12345"))
        self.assertIsNone(mal.target(FakeCursor(mapping=("season", None, None, "s"), anime=False), "12345"))
        self.assertEqual(mal.target(FakeCursor(mapping=("season", None, None, "s")), "12345"),
                         ("season_id", "s"))


if __name__ == "__main__":
    unittest.main()
