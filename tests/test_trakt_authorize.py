"""Contract and secret-handling checks for the local Trakt device flow."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trakt-sync/authorize.py"
spec = importlib.util.spec_from_file_location("marquee_trakt_authorize", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TraktAuthorizationTests(unittest.TestCase):
    def test_pending_then_approved_without_printing_tokens(self):
        calls, messages, now = [], [], [0]
        replies = iter([
            (200, {"device_code": "device-private", "user_code": "ABC12345",
                   "verification_url": "https://trakt.tv/activate", "interval": 2, "expires_in": 60}),
            (400, None),
            (200, {"access_token": "access-private", "refresh_token": "refresh-private"}),
        ])

        def request(url, body):
            calls.append((url, body))
            return next(replies)

        def sleep(seconds):
            now[0] += seconds

        tokens = module.authorize("id", "secret", request=request, sleep=sleep,
                                  clock=lambda: now[0], announce=messages.append)
        self.assertEqual(tokens, ("access-private", "refresh-private"))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]["code"], "device-private")
        self.assertNotIn("private", " ".join(messages))

    def test_slow_down_and_expired_code(self):
        now = [0]
        replies = iter([
            (200, {"device_code": "device", "user_code": "ABCDEFGH",
                   "verification_url": "https://trakt.tv/activate", "interval": 1, "expires_in": 8}),
            (429, None),
            (400, None),
        ])
        with self.assertRaisesRegex(module.AuthorizationError, "expired"):
            module.authorize("id", "secret", request=lambda *_: next(replies),
                             sleep=lambda n: now.__setitem__(0, now[0] + n),
                             clock=lambda: now[0], announce=lambda *_: None)

    def test_secrets_go_to_stdin_and_fail_closed(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return type("Result", (), {"returncode": 1 if len(calls) == 3 else 0})()

        with self.assertRaisesRegex(module.AuthorizationError, "TRAKT_ACCESS_TOKEN"):
            module.install_secrets("id-private", "secret-private", "access-private",
                                   "refresh-private", run=run)
        self.assertEqual([v[0][3] for v in calls],
                         ["TRAKT_CLIENT_SECRET", "TRAKT_REFRESH_TOKEN", "TRAKT_ACCESS_TOKEN"])
        for argv, kwargs in calls:
            self.assertFalse(any("private" in arg for arg in argv))
            self.assertEqual(kwargs["stdout"], module.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], module.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
