"""Check token bundle switching and secret storage without network access."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import unittest


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
    def test_bundle_takes_precedence_and_bad_bundle_never_falls_back(self):
        self.assertEqual(run_with_oauth.credential_pair("", "old-id", "old-token"),
                         ("old-id", "old-token"))
        bundle = json.dumps({"client_id": "new-id", "access_token": "new-token",
                             "refresh_token": "refresh-private"})
        self.assertEqual(run_with_oauth.credential_pair(bundle, "old-id", "old-token"),
                         ("new-id", "new-token"))
        with self.assertRaisesRegex(ValueError, "invalid"):
            run_with_oauth.credential_pair("{}", "old-id", "old-token")

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
