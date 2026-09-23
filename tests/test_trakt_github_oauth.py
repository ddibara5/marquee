"""Check token bundle switching and secret storage without network access."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from io import BytesIO


ROOT = Path(__file__).resolve().parents[1] / "scripts/trakt-sync"
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


github_authorize = load("github_authorize")
run_with_oauth = load("run_with_oauth")


class GitHubTraktTests(unittest.TestCase):
    def test_bundle_validation(self):
        bundle = json.dumps({"client_id": "new-id", "access_token": "new-token",
                             "refresh_token": "refresh-private",
                             "issued_at": "2026-09-23T00:00:00+00:00"})
        self.assertEqual(run_with_oauth.parse_bundle(bundle)["access_token"], "new-token")
        with self.assertRaisesRegex(run_with_oauth.RefreshError, "invalid"):
            run_with_oauth.parse_bundle("{}")

    def test_refresh_rotates_pair_and_persists_before_import(self):
        old = {"client_id": "id", "access_token": "old", "refresh_token": "old-refresh",
               "issued_at": "2026-09-17T00:00:00+00:00"}
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        self.assertTrue(run_with_oauth.due_for_refresh(old, now=now))
        observed = {}

        def opener(request, timeout):
            observed["request"] = json.loads(request.data)
            return BytesIO(json.dumps({"access_token": "new", "refresh_token": "new-refresh"}).encode())

        updated = run_with_oauth.refresh(old, "client-private", "urn:ietf:wg:oauth:2.0:oob",
                                         opener=opener, now=now)
        self.assertEqual(observed["request"]["grant_type"], "refresh_token")
        self.assertEqual(updated["refresh_token"], "new-refresh")
        self.assertEqual(updated["issued_at"], now.isoformat())
        calls = []

        def persist_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return type("Result", (), {"returncode": 0})()

        run_with_oauth.persist(updated, run=persist_run)
        self.assertEqual(json.loads(calls[0][1]["input"])["refresh_token"], "new-refresh")
        self.assertFalse(any("private" in item for item in calls[0][0]))
        self.assertEqual(calls[0][1]["stderr"], run_with_oauth.subprocess.DEVNULL)

    def test_failed_persistence_prevents_database_import(self):
        bundle = json.dumps({"client_id": "id", "access_token": "old",
                             "refresh_token": "old-refresh",
                             "issued_at": "2020-01-01T00:00:00+00:00"})
        environment = {"TRAKT_OAUTH_BUNDLE": bundle, "TRAKT_MARQUEE_CLIENT_ID": "id",
                       "TRAKT_MARQUEE_CLIENT_SECRET": "private", "TRAKT_MARQUEE_REDIRECT_URI": "uri",
                       "GH_TOKEN": "private"}
        with patch.dict(run_with_oauth.os.environ, environment, clear=True), \
             patch.object(run_with_oauth, "refresh", return_value=json.loads(bundle)), \
             patch.object(run_with_oauth, "persist", side_effect=run_with_oauth.RefreshError("write failed")), \
             patch.object(run_with_oauth.subprocess, "run") as importer:
            self.assertEqual(run_with_oauth.main(), 1)
            importer.assert_not_called()

    def test_recent_bundle_invokes_import_without_writer_credentials(self):
        bundle = json.dumps({"client_id": "id", "access_token": "access",
                             "refresh_token": "refresh",
                             "issued_at": datetime.now(timezone.utc).isoformat()})
        environment = {"TRAKT_OAUTH_BUNDLE": bundle, "TRAKT_MARQUEE_CLIENT_ID": "id",
                       "GH_TOKEN": "private", "TRAKT_MARQUEE_CLIENT_SECRET": "private"}
        with patch.dict(run_with_oauth.os.environ, environment, clear=True), \
             patch.object(run_with_oauth.subprocess, "run") as importer:
            importer.return_value.returncode = 0
            self.assertEqual(run_with_oauth.main(), 0)
            child = importer.call_args.kwargs["env"]
            self.assertEqual(child["TRAKT_ACCESS_TOKEN"], "access")
            self.assertNotIn("GH_TOKEN", child)
            self.assertNotIn("TRAKT_OAUTH_BUNDLE", child)

    def test_explicit_refresh_rotates_recent_bundle_before_import(self):
        bundle = json.dumps({"client_id": "id", "access_token": "old",
                             "refresh_token": "refresh",
                             "issued_at": datetime.now(timezone.utc).isoformat()})
        environment = {"TRAKT_OAUTH_BUNDLE": bundle, "TRAKT_MARQUEE_CLIENT_ID": "id",
                       "TRAKT_MARQUEE_CLIENT_SECRET": "private",
                       "TRAKT_MARQUEE_REDIRECT_URI": "uri", "GH_TOKEN": "private",
                       "REFRESH_NOW": "true"}
        updated = dict(json.loads(bundle), access_token="new")
        with patch.dict(run_with_oauth.os.environ, environment, clear=True), \
             patch.object(run_with_oauth, "refresh", return_value=updated) as refresh, \
             patch.object(run_with_oauth, "persist") as persist, \
             patch.object(run_with_oauth.subprocess, "run") as importer:
            importer.return_value.returncode = 0
            self.assertEqual(run_with_oauth.main(), 0)
            refresh.assert_called_once()
            persist.assert_called_once_with(updated)
            self.assertEqual(importer.call_args.kwargs["env"]["TRAKT_ACCESS_TOKEN"], "new")

    def test_bundle_is_single_secret_sent_only_on_stdin(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return type("Result", (), {"returncode": 0})()

        github_authorize.save_bundle("id-private", "access-private", "refresh-private",
                                     run=run, which=lambda _: "gh",
                                     now=lambda: datetime(2026, 9, 23, tzinfo=timezone.utc))
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        self.assertEqual(argv[3], "TRAKT_OAUTH_BUNDLE")
        self.assertFalse(any("private" in item for item in argv))
        self.assertEqual(json.loads(kwargs["input"])["refresh_token"], "refresh-private")
        self.assertEqual(kwargs["stdout"], github_authorize.subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], github_authorize.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
