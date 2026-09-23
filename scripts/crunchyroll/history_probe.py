#!/usr/bin/env python3
"""Read-only Crunchyroll history coverage probe. Never emits raw private records."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import base64
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


BASE = "https://www.crunchyroll.com"
# Public web client ID observed in open-source Crunchyroll clients. It can change.
CLIENT_ID = "noaihdevm_6iyg0a8l0q"
PAGE_SIZE = 100
MAX_PAGES = 500


class ProbeError(RuntimeError):
    pass


def request_json(request, *, opener=urlopen, sleep=time.sleep):
    for attempt in range(4):
        try:
            with opener(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise ProbeError(f"Crunchyroll request failed (HTTP {exc.code})") from None
            delay = min(2 ** attempt, 8)
            retry_after = exc.headers.get("Retry-After")
            if retry_after and retry_after.isdecimal():
                delay = min(int(retry_after), 30)
            sleep(delay)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 3:
                raise ProbeError("Crunchyroll connection failed") from None
            sleep(min(2 ** attempt, 8))
        except (ValueError, UnicodeError):
            raise ProbeError("Crunchyroll returned non-JSON data") from None
    raise AssertionError("retry loop exhausted")


def request_stage(request, stage, *, requester):
    """Identify a failed step without logging its URL, headers, or response."""
    try:
        return requester(request)
    except ProbeError as exc:
        raise ProbeError(f"{stage}: {exc}") from None


def bearer_from_cookie(cookie, *, requester=request_json):
    if not cookie or "\r" in cookie or "\n" in cookie:
        raise ProbeError("CRUNCHYROLL_ETP_RT is missing or invalid")
    client_id = os.environ.get("CRUNCHYROLL_PUBLIC_CLIENT_ID", CLIENT_ID).strip()
    if not client_id:
        raise ProbeError("Public client ID is missing")
    basic = base64.b64encode(f"{client_id}:".encode()).decode()
    body = urlencode({"grant_type": "etp_rt_cookie", "scope": "offline_access",
                      "device_id": str(uuid4()), "device_name": "Marquee history probe",
                      "device_type": "com.crunchyroll.desktop.windows"}).encode()
    request = Request(BASE + "/auth/v1/token", data=body, method="POST",
                      headers={"Authorization": "Basic " + basic, "Cookie": "etp_rt=" + cookie,
                               "Content-Type": "application/x-www-form-urlencoded",
                               "User-Agent": "MarqueeHistoryProbe/1.0"})
    payload = request_stage(request, "Token exchange", requester=requester)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ProbeError("Crunchyroll authentication response changed shape")
    return token


def get_account_id(token, *, requester=request_json):
    request = Request(BASE + "/accounts/v1/me",
                      headers={"Authorization": "Bearer " + token,
                               "User-Agent": "MarqueeHistoryProbe/1.0"})
    payload = request_stage(request, "Account lookup", requester=requester)
    account_id = payload.get("account_id") if isinstance(payload, dict) else None
    if not isinstance(account_id, str) or not account_id:
        raise ProbeError("Crunchyroll account response changed shape")
    return account_id, sorted(payload)


def history_request(account_id, token, page, page_size=PAGE_SIZE):
    url = (BASE + "/content/v2/" + account_id + "/watch-history?" +
           urlencode({"page": page, "page_size": page_size, "locale": "en-US",
                      "preferred_audio_language": "en-US"}))
    return Request(url, headers={"Authorization": "Bearer " + token,
                                 "Accept": "application/json",
                                 "User-Agent": "MarqueeHistoryProbe/1.0"})


def boundary_checks(account_id, token, *, requester=request_json):
    """Check page-number versus offset limits without emitting private records."""
    results = []
    for page in (11, 51):
        request = history_request(account_id, token, page, page_size=20)
        try:
            payload = request_stage(request, f"Boundary page {page}", requester=requester)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                results.append({"page": page, "page_size": 20, "status": "changed_shape"})
            else:
                results.append({"page": page, "page_size": 20,
                                "status": "ok", "records": len(payload["data"])})
        except ProbeError as exc:
            # Only report our own fixed error categories; never echo a response.
            status = "http_400" if str(exc).endswith("(HTTP 400)") else "request_failed"
            results.append({"page": page, "page_size": 20, "status": status})
    return results


def legacy_history_pages(account_id, token, *, requester=request_json,
                         sleep=time.sleep, max_pages=MAX_PAGES):
    """Follow the older endpoint's next_page, confined to this account and host."""
    if not isinstance(account_id, str) or not account_id or "/" in account_id:
        raise ProbeError("Invalid account identifier")
    path = "/content/v1/watch-history/" + account_id
    url = BASE + path + "?" + urlencode({"locale": "en-US", "page": 1,
                                          "page_size": 20})
    seen_urls, seen_pages = set(), set()
    for page in range(1, max_pages + 1):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "www.crunchyroll.com"
                or parsed.path != path or parsed.fragment or url in seen_urls):
            raise ProbeError("Legacy pagination link is invalid or repeated")
        seen_urls.add(url)
        request = Request(url, headers={"Authorization": "Bearer " + token,
                                        "Accept": "application/json",
                                        "User-Agent": "MarqueeHistoryProbe/1.0"})
        payload = request_stage(request, f"Legacy history page {page}", requester=requester)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProbeError("Legacy history response changed shape")
        items = payload["items"]
        if any(not isinstance(item, dict) for item in items):
            raise ProbeError("Legacy history item changed shape")
        if items:
            signature = json.dumps(items, sort_keys=True, separators=(",", ":"))
            if signature in seen_pages:
                raise ProbeError("Legacy history returned the same page twice")
            seen_pages.add(signature)
            yield items
        next_page = payload.get("next_page")
        if next_page is None or next_page == "":
            return
        if not isinstance(next_page, str) or not next_page.startswith(("/", "?")):
            raise ProbeError("Legacy pagination link changed shape")
        url = urljoin(url, next_page)
        sleep(0.2)
    raise ProbeError("Legacy page limit reached before finding the end of history")


def history_pages(account_id, token, *, requester=request_json, sleep=time.sleep,
                  max_pages=MAX_PAGES, envelope_keys=None, envelope_info=None):
    if not isinstance(account_id, str) or not account_id or "/" in account_id:
        raise ProbeError("Invalid account identifier")
    seen_pages = set()
    for page in range(1, max_pages + 1):
        request = history_request(account_id, token, page)
        payload = request_stage(request, f"History page {page}", requester=requester)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProbeError("Crunchyroll history response changed shape")
        if envelope_keys is not None:
            envelope_keys.update(payload)
        if envelope_info is not None and page == 1:
            total = payload.get("total")
            envelope_info["reported_total"] = total if type(total) is int and total >= 0 else None
            meta = payload.get("meta")
            envelope_info["meta_field_names"] = sorted(meta) if isinstance(meta, dict) else []
        items = payload["data"]
        if not items:
            return
        if any(not isinstance(item, dict) for item in items):
            raise ProbeError("Crunchyroll history item changed shape")
        # A broken server/page parameter must not be mistaken for a complete fetch.
        signature = json.dumps(items, sort_keys=True, separators=(",", ":"))
        if signature in seen_pages:
            raise ProbeError("Crunchyroll returned the same history page twice")
        seen_pages.add(signature)
        yield items
        sleep(0.2)
    raise ProbeError("Page limit reached before finding the end of history")


def summarize(pages, *, account_keys=None):
    counts = Counter()
    event_keys, panel_keys, metadata_keys = set(), set(), set()
    episode_ids = Counter()
    dates = []
    pages_read = 0
    page_sizes = []
    for items in pages:
        pages_read += 1
        page_sizes.append(len(items))
        counts["records"] += len(items)
        for item in items:
            event_keys.update(item)
            panel = item.get("panel")
            if not isinstance(panel, dict):
                counts["missing_panel"] += 1
                panel = {}
            panel_keys.update(panel)
            metadata = panel.get("episode_metadata")
            if isinstance(metadata, dict):
                metadata_keys.update(metadata)
            else:
                counts["missing_episode_metadata"] += 1
            episode_id = panel.get("id")
            if isinstance(episode_id, str) and episode_id:
                episode_ids[episode_id] += 1
            else:
                counts["missing_episode_id"] += 1
            if item.get("fully_watched") is True:
                counts["fully_watched"] += 1
            value = item.get("date_played")
            if not isinstance(value, str) or not value:
                counts["missing_date_played"] += 1
                continue
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
                dates.append(parsed.astimezone(timezone.utc))
            except ValueError:
                counts["invalid_date_played"] += 1
    if not counts["records"]:
        raise ProbeError("History is empty; verify the selected Crunchyroll profile")
    return {"pages": pages_read, "page_sizes": page_sizes,
            "records": counts["records"],
            "unique_episode_ids": len(episode_ids),
            "repeat_episode_observations": sum(n - 1 for n in episode_ids.values()),
            "fully_watched": counts["fully_watched"],
            "missing_panel": counts["missing_panel"],
            "missing_episode_metadata": counts["missing_episode_metadata"],
            "missing_episode_id": counts["missing_episode_id"],
            "missing_date_played": counts["missing_date_played"],
            "invalid_date_played": counts["invalid_date_played"],
            "oldest_date_played_utc": min(dates).isoformat() if dates else None,
            "newest_date_played_utc": max(dates).isoformat() if dates else None,
            "field_names": {"account": account_keys or [], "event": sorted(event_keys),
                            "panel": sorted(panel_keys), "episode_metadata": sorted(metadata_keys)},
            "profile_scope": "unverified; compare with the selected website profile"}


def identity_diagnostics(pages):
    """Count usable source IDs without emitting identifiers or record contents."""
    counts = Counter()
    event_ids, missing_panel_parents = Counter(), Counter()
    for items in pages:
        for item in items:
            event_id = item.get("id")
            if isinstance(event_id, str) and event_id:
                event_ids[event_id] += 1
            else:
                counts["missing_event_id"] += 1
            parent_id = item.get("parent_id")
            panel = item.get("panel")
            panel_id = panel.get("id") if isinstance(panel, dict) else None
            if isinstance(panel_id, str) and panel_id:
                counts["panel_id_present"] += 1
                if isinstance(parent_id, str) and parent_id:
                    counts["parent_id_with_panel"] += 1
                    if parent_id == panel_id:
                        counts["parent_matches_panel_id"] += 1
            else:
                counts["panel_id_missing"] += 1
                if isinstance(parent_id, str) and parent_id:
                    counts["parent_id_without_panel"] += 1
                    missing_panel_parents[parent_id] += 1
    return {"missing_event_id": counts["missing_event_id"],
            "unique_event_ids": len(event_ids),
            "duplicate_event_id_observations": sum(n - 1 for n in event_ids.values()),
            "panel_id_present": counts["panel_id_present"],
            "panel_id_missing": counts["panel_id_missing"],
            "parent_id_with_panel": counts["parent_id_with_panel"],
            "parent_matches_panel_id": counts["parent_matches_panel_id"],
            "parent_id_without_panel": counts["parent_id_without_panel"],
            "unique_parent_ids_without_panel": len(missing_panel_parents)}


def feed_overlap(v1_pages, v2_pages):
    """Compare stable event IDs across feeds; keep the ID values private."""
    v1 = {item["id"]: item for page in v1_pages for item in page
          if isinstance(item.get("id"), str) and item["id"]}
    v2 = {item["id"]: item for page in v2_pages for item in page
          if isinstance(item.get("id"), str) and item["id"]}
    common = v1.keys() & v2.keys()
    return {"common_event_ids": len(common),
            "v2_ids_absent_from_v1": len(v2.keys() - v1.keys()),
            "v1_ids_absent_from_v2": len(v1.keys() - v2.keys()),
            "common_ids_same_date_played": sum(
                v1[key].get("date_played") == v2[key].get("date_played") for key in common),
            "common_ids_same_panel_id": sum(
                isinstance(v1[key].get("panel"), dict)
                and isinstance(v2[key].get("panel"), dict)
                and v1[key]["panel"].get("id") == v2[key]["panel"].get("id")
                for key in common)}


def main():
    pages = []
    envelope_keys = set()
    envelope_info = {}
    try:
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, keys = get_account_id(token)
        for page in history_pages(account_id, token, envelope_keys=envelope_keys,
                                  envelope_info=envelope_info):
            pages.append(page)
        result = summarize(pages, account_keys=keys)
        result["history_envelope_keys"] = sorted(envelope_keys)
        result.update(envelope_info)
    except ProbeError as exc:
        if pages:
            # A boundary error must remain a failure, but coverage observed so far
            # can help distinguish a short final page from a server-side page cap.
            observed = summarize(pages, account_keys=keys)
            observed["history_envelope_keys"] = sorted(envelope_keys)
            observed.update(envelope_info)
            print(json.dumps({"coverage": "incomplete", "observed":
                              observed}, sort_keys=True))
            if str(exc).startswith("History page 11:") and "(HTTP 400)" in str(exc):
                print(json.dumps({"boundary_checks": boundary_checks(account_id, token)},
                                 sort_keys=True))
                legacy_pages = []
                try:
                    for page in legacy_history_pages(account_id, token):
                        legacy_pages.append(page)
                    legacy = summarize(legacy_pages, account_keys=keys)
                    overlap = feed_overlap(legacy_pages, pages)
                    if not overlap["common_event_ids"]:
                        raise ProbeError("Legacy history has no matching event IDs")
                    print(json.dumps({"coverage": "legacy_next_page_end_observed",
                                      "feed_overlap": overlap,
                                      "identity_diagnostics": identity_diagnostics(legacy_pages),
                                      "observed": legacy}, sort_keys=True))
                    return 0
                except ProbeError as legacy_exc:
                    if legacy_pages:
                        print(json.dumps({"coverage": "legacy_incomplete",
                                          "observed": summarize(legacy_pages,
                                                                account_keys=keys)},
                                         sort_keys=True))
                    print(f"Legacy probe failed: {legacy_exc}", file=sys.stderr)
        print(f"Crunchyroll probe failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
