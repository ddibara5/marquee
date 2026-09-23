#!/usr/bin/env python3
"""Complete Trakt device authorization inside a manually dispatched Action.

Only the short user code is logged. The issued tokens are stored together in
one encrypted GitHub Actions secret by a repository-scoped Secrets-write token.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys

from authorize import AuthorizationError, authorize


REPO = "ddibara5/marquee"
SECRET_NAME = "TRAKT_OAUTH_BUNDLE"


def save_bundle(client_id, access_token, refresh_token, *, run=subprocess.run,
                which=shutil.which, now=lambda: datetime.now(timezone.utc)):
    if not which("gh"):
        raise AuthorizationError("GitHub CLI is unavailable on this runner")
    bundle = json.dumps({"client_id": client_id, "access_token": access_token,
                         "refresh_token": refresh_token, "issued_at": now().isoformat()},
                        separators=(",", ":"))
    result = run(["gh", "secret", "set", SECRET_NAME, "--repo", REPO, "--app", "actions"],
                 input=bundle, text=True, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise AuthorizationError("GitHub could not store the new token bundle; reauthorize before importing")


def main():
    client_id = os.environ.get("TRAKT_MARQUEE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("TRAKT_MARQUEE_CLIENT_SECRET", "").strip()
    writer = os.environ.get("GH_TOKEN", "").strip()
    if not client_id or not client_secret or not writer:
        raise AuthorizationError("Missing Marquee app credentials or repository Secrets-write token")
    if not shutil.which("gh"):
        raise AuthorizationError("GitHub CLI is unavailable on this runner")
    preflight = subprocess.run(["gh", "secret", "list", "--repo", REPO, "--app", "actions"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False)
    if preflight.returncode:
        raise AuthorizationError("Secrets-write token cannot access Marquee Actions secrets")
    access_token, refresh_token = authorize(client_id, client_secret)
    save_bundle(client_id, access_token, refresh_token)
    print("Marquee authorization saved to GitHub Actions secrets. Import remains manual.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AuthorizationError as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        sys.exit(1)
