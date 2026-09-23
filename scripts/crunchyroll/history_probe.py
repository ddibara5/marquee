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
from urllib.parse import urlencode
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
    payload = requester(request)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ProbeError("Crunchyroll authentication response changed shape")
    return token


def get_account_id(token, *, requester=request_json):
    request = Request(BASE + "/accounts/v1/me",
                      headers={"Authorization": "Bearer " + token,
                               "User-Agent": "MarqueeHistoryProbe/1.0"})
    payload = requester(request)
    account_id = payload.get("account_id") if isinstance(payload, dict) else None
    if not isinstance(account_id, str) or not account_id:
        raise ProbeError("Crunchyroll account response changed shape")
    return account_id, sorted(payload)


def history_pages(account_id, token, *, requester=request_json, sleep=time.sleep,
                  max_pages=MAX_PAGES):
    if not isinstance(account_id, str) or not account_id or "/" in account_id:
        raise ProbeError("Invalid account identifier")
    seen_pages = set()
    for page in range(1, max_pages + 1):
        url = (BASE + "/content/v2/" + account_id + "/watch-history?" +
               urlencode({"page": page, "page_size": PAGE_SIZE, "locale": "en-US",
                          "preferred_audio_language": "en-US"}))
        request = Request(url, headers={"Authorization": "Bearer " + token,
                                       "Accept": "application/json",
                                       "User-Agent": "MarqueeHistoryProbe/1.0"})
        payload = requester(request)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProbeError("Crunchyroll history response changed shape")
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
    for items in pages:
        pages_read += 1
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
    return {"pages": pages_read, "records": counts["records"],
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


def main():
    try:
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, keys = get_account_id(token)
        result = summarize(history_pages(account_id, token), account_keys=keys)
    except ProbeError as exc:
        print(f"Crunchyroll probe failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
