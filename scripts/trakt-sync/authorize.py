#!/usr/bin/env python3
"""Authorize Dave's Marquee Trakt app locally and set GitHub Actions secrets.

Run only on a trusted computer with GitHub CLI already authenticated. Token
values are passed to gh on stdin; neither token is printed or saved to disk.
"""

from __future__ import annotations

import getpass
import json
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO = "ddibara5/marquee"
BASE = "https://auth.trakt.tv/oauth/device"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json",
           "User-Agent": "MarqueeTraktAuth/1.0 (github.com/ddibara5/marquee)"}


class AuthorizationError(RuntimeError):
    pass


def post(url, body, opener=urlopen):
    request = Request(url, data=json.dumps(body).encode(), headers=HEADERS, method="POST")
    try:
        with opener(request, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        # Never print the request or HTTP response. They may contain credentials.
        return exc.code, None
    except (URLError, TimeoutError) as exc:
        raise AuthorizationError("Trakt connection failed") from exc


def authorize(client_id, client_secret, *, request=post, sleep=time.sleep,
              clock=time.monotonic, announce=print):
    status, challenge = request(BASE + "/code", {"client_id": client_id})
    if status != 200 or not isinstance(challenge, dict):
        raise AuthorizationError(f"Trakt device code request failed (HTTP {status})")
    try:
        device_code = challenge["device_code"]
        user_code = challenge["user_code"]
        verification_url = challenge["verification_url"]
        interval = challenge["interval"]
        expires_in = challenge["expires_in"]
        if not all(isinstance(x, str) and x for x in (device_code, user_code, verification_url)):
            raise ValueError
        if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 120:
            raise ValueError
        if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in < interval:
            raise ValueError
        if not verification_url.startswith("https://"):
            raise ValueError
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthorizationError("Trakt device challenge changed shape") from exc

    announce(f"Open {verification_url} and enter code {user_code} to authorize Marquee.")
    deadline = clock() + expires_in
    delay = interval
    while clock() + delay < deadline:
        sleep(delay)
        status, payload = request(BASE + "/token", {
            "code": device_code, "client_id": client_id, "client_secret": client_secret})
        if status == 200:
            if not isinstance(payload, dict) or not all(
                    isinstance(payload.get(name), str) and payload[name]
                    for name in ("access_token", "refresh_token")):
                raise AuthorizationError("Trakt returned incomplete tokens")
            return payload["access_token"], payload["refresh_token"]
        if status == 400:  # Authorization pending.
            continue
        if status == 429:  # Trakt asks us to slow down.
            delay += 5
            continue
        raise AuthorizationError(f"Trakt device authorization stopped (HTTP {status})")
    raise AuthorizationError("Trakt device code expired; restart authorization")


def ensure_github_cli(run=subprocess.run):
    if not shutil.which("gh"):
        raise AuthorizationError("Install GitHub CLI and run gh auth login first")
    result = run(["gh", "auth", "status", "--active", "--hostname", "github.com"],
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise AuthorizationError("Authenticate GitHub CLI with an account that can edit Marquee secrets")
    result = run(["gh", "secret", "list", "--repo", REPO, "--app", "actions"],
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise AuthorizationError("GitHub CLI cannot access Marquee Actions secrets")


def install_secrets(client_id, client_secret, access_token, refresh_token,
                    *, run=subprocess.run):
    # Keep the old access token paired with the old client ID until the last
    # two writes. Do not dispatch the manual import during this transition.
    for name, value in (("TRAKT_CLIENT_SECRET", client_secret),
                        ("TRAKT_REFRESH_TOKEN", refresh_token),
                        ("TRAKT_ACCESS_TOKEN", access_token),
                        ("TRAKT_CLIENT_ID", client_id)):
        result = run(["gh", "secret", "set", name, "--repo", REPO, "--app", "actions"],
                     input=value, text=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, check=False)
        if result.returncode:
            raise AuthorizationError(f"Could not save {name}; keep all runs manual and retry authorization")


def main():
    ensure_github_cli()
    print("Marquee Trakt authorization. Do not run the manual import until setup completes.")
    client_id = getpass.getpass("Marquee app client ID (hidden): ").strip()
    client_secret = getpass.getpass("Marquee app client secret (hidden): ").strip()
    if not client_id or not client_secret:
        raise AuthorizationError("Both Marquee app credentials are required")
    access_token, refresh_token = authorize(client_id, client_secret)
    install_secrets(client_id, client_secret, access_token, refresh_token)
    print("Marquee Trakt credentials saved to GitHub Actions secrets. No schedule is active.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AuthorizationError as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        sys.exit(1)
