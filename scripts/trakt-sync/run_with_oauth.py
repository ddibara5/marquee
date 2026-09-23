#!/usr/bin/env python3
"""Refresh the Marquee Trakt token when due, then run the importer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from github_authorize import REPO, SECRET_NAME

TOKEN_URL = "https://auth.trakt.tv/oauth/token"
TOKEN_LIFETIME = timedelta(days=7)
REFRESH_MARGIN = timedelta(days=2)


class RefreshError(RuntimeError):
    pass


def parse_bundle(bundle):
    try:
        data = json.loads(bundle)
        if not isinstance(data, dict) or not all(
            isinstance(data.get(key), str) and data[key]
            for key in ("client_id", "access_token", "refresh_token", "issued_at")
        ):
            raise ValueError
        if datetime.fromisoformat(data["issued_at"]).tzinfo is None:
            raise ValueError
        return data
    except (ValueError, TypeError) as exc:
        raise RefreshError("Marquee Trakt token bundle is invalid; reauthorize") from exc


def due_for_refresh(data, *, now):
    issued_at = datetime.fromisoformat(data["issued_at"])
    return now >= issued_at + TOKEN_LIFETIME - REFRESH_MARGIN


def refresh(data, client_secret, redirect_uri, *, opener=urlopen, now):
    if not client_secret or not redirect_uri:
        raise RefreshError("Marquee app secret or redirect URI is missing; no import was run")
    body = {"client_id": data["client_id"], "client_secret": client_secret,
            "refresh_token": data["refresh_token"], "redirect_uri": redirect_uri,
            "grant_type": "refresh_token"}
    request = Request(TOKEN_URL, data=json.dumps(body).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json",
                               "User-Agent": "MarqueeTraktSync/1.0 (github.com/ddibara5/marquee)"})
    try:
        with opener(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RefreshError(f"Trakt token refresh rejected (HTTP {exc.code}); no import was run") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RefreshError("Trakt token refresh connection failed; no import was run") from exc
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), str) and payload[key]
        for key in ("access_token", "refresh_token")
    ):
        raise RefreshError("Trakt returned incomplete refresh tokens; reauthorize before importing")
    return {"client_id": data["client_id"], "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"], "issued_at": now.isoformat()}


def persist(data, *, run=subprocess.run):
    result = run(["gh", "secret", "set", SECRET_NAME, "--repo", REPO, "--app", "actions"],
                 input=json.dumps(data, separators=(",", ":")), text=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise RefreshError("GitHub could not save rotated Trakt tokens; reauthorize before importing")


def main():
    bundle = os.environ.get("TRAKT_OAUTH_BUNDLE", "")
    if not bundle:
        print("TRAKT_OAUTH_BUNDLE is missing; authorize Marquee before importing", file=sys.stderr)
        return 1
    try:
        data = parse_bundle(bundle)
        if data["client_id"] != os.environ.get("TRAKT_MARQUEE_CLIENT_ID", ""):
            raise RefreshError("Marquee client ID differs from token bundle; no import was run")
        current = datetime.now(timezone.utc)
        if due_for_refresh(data, now=current) or os.environ.get("REFRESH_NOW") == "true":
            if not os.environ.get("GH_TOKEN"):
                raise RefreshError("Secrets-write token is missing; no import was run")
            data = refresh(data, os.environ.get("TRAKT_MARQUEE_CLIENT_SECRET", ""),
                           os.environ.get("TRAKT_MARQUEE_REDIRECT_URI", ""), now=current)
            persist(data)
            print("Rotated Trakt tokens saved before import.")
    except RefreshError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["TRAKT_CLIENT_ID"], env["TRAKT_ACCESS_TOKEN"] = data["client_id"], data["access_token"]
    for name in ("TRAKT_OAUTH_BUNDLE", "GH_TOKEN", "TRAKT_MARQUEE_CLIENT_SECRET", "REFRESH_NOW"):
        env.pop(name, None)
    return subprocess.run([sys.executable, "scripts/trakt-sync/trakt_sync.py", *sys.argv[1:]],
                          env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
