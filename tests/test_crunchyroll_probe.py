"""Offline contract tests for the read-only Crunchyroll history probe."""

import importlib.util
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "history_probe", ROOT / "scripts/crunchyroll/history_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CrunchyrollProbeTests(unittest.TestCase):
    def test_pages_continue_to_empty_even_after_short_page(self):
        fixture = json.loads((ROOT / "fixtures/crunchyroll/history_pages.json").read_text())
        seen = []

        def requester(request):
            seen.append(request.full_url)
            page = int(request.full_url.split("page=")[1].split("&")[0])
            return {"data": fixture[page - 1] if page <= len(fixture) else []}

        pages = list(probe.history_pages("fake-account", "fake-token", requester=requester,
                                         sleep=lambda _: None))
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(seen), 3)
        result = probe.summarize(pages, account_keys=["account_id"])
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["page_sizes"], [2, 1])
        self.assertEqual(result["unique_episode_ids"], 2)
        self.assertEqual(result["repeat_episode_observations"], 1)
        self.assertTrue(result["oldest_date_played_utc"].startswith("2026-01-09"))
        self.assertNotIn("Fabricated episode", json.dumps(result))
        self.assertNotIn("fake-account", json.dumps(result))

    def test_repeated_page_and_contract_break_fail_instead_of_partial_success(self):
        fixture = json.loads((ROOT / "fixtures/crunchyroll/history_pages.json").read_text())
        with self.assertRaisesRegex(probe.ProbeError, "same history page"):
            list(probe.history_pages("account", "token", requester=lambda _: {"data": fixture[0]},
                                     sleep=lambda _: None))
        with self.assertRaisesRegex(probe.ProbeError, "changed shape"):
            list(probe.history_pages("account", "token", requester=lambda _: {"items": []},
                                     sleep=lambda _: None))

    def test_auth_error_does_not_reveal_cookie_or_response(self):
        def requester(request):
            self.assertIn("private-cookie", request.get_header("Cookie"))
            raise HTTPError(request.full_url, 401, "private-response", {}, None)

        with self.assertRaises(probe.ProbeError) as raised:
            probe.bearer_from_cookie("private-cookie", requester=lambda req: probe.request_json(
                req, opener=lambda *args, **kwargs: requester(req)))
        self.assertNotIn("private-cookie", str(raised.exception))
        self.assertNotIn("private-response", str(raised.exception))
        self.assertIn("Token exchange", str(raised.exception))

    def test_request_stages_are_safe_and_specific(self):
        def fail(_):
            raise probe.ProbeError("Crunchyroll request failed (HTTP 400)")

        with self.assertRaisesRegex(probe.ProbeError, "Account lookup:.*HTTP 400"):
            probe.get_account_id("secret-token", requester=fail)
        with self.assertRaisesRegex(probe.ProbeError, "History page 1:.*HTTP 400"):
            list(probe.history_pages("private-account", "secret-token", requester=fail))

    def test_boundary_failure_retains_only_safe_observations(self):
        fixture = json.loads((ROOT / "fixtures/crunchyroll/history_pages.json").read_text())
        pages = []

        def requester(request):
            page = int(request.full_url.split("page=")[1].split("&")[0])
            if page == 3:
                raise probe.ProbeError("Crunchyroll request failed (HTTP 400)")
            return {"data": fixture[page - 1]}

        with self.assertRaisesRegex(probe.ProbeError, "History page 3"):
            for page in probe.history_pages("private-account", "secret-token",
                                            requester=requester, sleep=lambda _: None):
                pages.append(page)
        observed = json.dumps(probe.summarize(pages))
        self.assertIn('"page_sizes": [2, 1]', observed)
        self.assertNotIn("private-account", observed)
        self.assertNotIn("Fabricated episode", observed)

    def test_boundary_checks_distinguish_page_and_offset_limits(self):
        def requester(request):
            from urllib.parse import parse_qs, urlsplit
            query = parse_qs(urlsplit(request.full_url).query)
            self.assertEqual(query["page_size"], ["20"])
            page = int(query["page"][0])
            if page == 51:
                raise probe.ProbeError("Crunchyroll request failed (HTTP 400)")
            return {"data": [{"id": "private-event"}] * 20}

        checks = probe.boundary_checks("private-account", "secret-token", requester=requester)
        self.assertEqual(checks, [{"page": 11, "page_size": 20, "status": "ok",
                                   "records": 20},
                                  {"page": 51, "page_size": 20, "status": "http_400"}])
        self.assertNotIn("private-event", json.dumps(checks))
        self.assertNotIn("secret-token", json.dumps(checks))

    def test_legacy_next_page_reads_to_end_without_emitting_records(self):
        urls = []

        def requester(request):
            urls.append(request.full_url)
            if len(urls) == 1:
                return {"items": [{"id": "private-event", "date_played":
                                    "2026-01-01T12:00:00Z", "panel": {"id": "episode"}}],
                        "next_page": "/content/v1/watch-history/fake-account?page=2"}
            return {"items": [{"id": "older-event", "date_played":
                                "2025-12-01T12:00:00Z", "panel": {"id": "episode"}}]}

        pages = list(probe.legacy_history_pages("fake-account", "secret-token",
                                                 requester=requester,
                                                 sleep=lambda _: None))
        self.assertEqual([len(page) for page in pages], [1, 1])
        self.assertEqual(len(urls), 2)
        self.assertEqual(probe.summarize(pages)["oldest_date_played_utc"],
                         "2025-12-01T12:00:00+00:00")

    def test_legacy_rejects_cross_host_link_before_sending_token(self):
        calls = []

        def requester(request):
            calls.append(request.full_url)
            return {"items": [{"id": "private-event"}],
                    "next_page": "//untrusted.example/content/v1/watch-history/account"}

        with self.assertRaisesRegex(probe.ProbeError, "pagination link"):
            list(probe.legacy_history_pages("account", "secret-token",
                                            requester=requester,
                                            sleep=lambda _: None))
        self.assertEqual(len(calls), 1)

    def test_v2_metadata_reports_only_safe_counts_and_field_names(self):
        envelope = {}
        pages = list(probe.history_pages("account", "token", envelope_info=envelope,
                                        requester=lambda _: {"data": [], "total": 1200,
                                                             "meta": {"next": "private-url"}}))
        self.assertEqual(pages, [])
        self.assertEqual(envelope, {"reported_total": 1200,
                                    "meta_field_names": ["next"]})


if __name__ == "__main__":
    unittest.main()
