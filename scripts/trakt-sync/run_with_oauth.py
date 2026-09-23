#!/usr/bin/env python3
"""Use the authorized Marquee token bundle or the prior manual Trakt token."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def credential_pair(bundle, legacy_id, legacy_token):
    if not bundle:
        if not legacy_id or not legacy_token:
            raise ValueError("Trakt credentials are missing")
        return legacy_id, legacy_token
    try:
        data = json.loads(bundle)
        client_id, token = data["client_id"], data["access_token"]
        if not isinstance(client_id, str) or not client_id or not isinstance(token, str) or not token:
            raise ValueError
        return client_id, token
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Marquee Trakt token bundle is invalid") from exc


def main():
    try:
        client_id, token = credential_pair(os.environ.get("TRAKT_OAUTH_BUNDLE"),
                                           os.environ.get("TRAKT_CLIENT_ID"),
                                           os.environ.get("TRAKT_ACCESS_TOKEN"))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["TRAKT_CLIENT_ID"], env["TRAKT_ACCESS_TOKEN"] = client_id, token
    env.pop("TRAKT_OAUTH_BUNDLE", None)
    return subprocess.run([sys.executable, "scripts/trakt-sync/trakt_sync.py", *sys.argv[1:]],
                          env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
