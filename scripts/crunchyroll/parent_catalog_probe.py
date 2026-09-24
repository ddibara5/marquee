#!/usr/bin/env python3
"""Read-only CMS lookup for missing-panel parent series; aggregate output only."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import sys
from urllib.parse import quote
from urllib.request import Request
from uuid import UUID

from history_probe import BASE, ProbeError, bearer_from_cookie, request_json, request_stage


def parent_snapshot(database_url, user_id):
    if not database_url:
        raise ProbeError("Database credential is missing")
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("set transaction read only")
                cur.execute("""select payload->>'parent_id',
                           payload #>> '{panel,episode_metadata,series_id}',
                           payload #>> '{panel,id}'
                    from public.marquee_ingest_raw
                    where source='crunchyroll' and source_entity_type='history_event'
                    and scope_key=%s""", (user_id,))
                rows = cur.fetchall()
                cur.execute("""select watermark->>'complete_event_count'
                    from public.marquee_sync_state
                    where source='crunchyroll' and scope_key=%s
                    and last_success_run_id is not null""", (user_id,))
                checkpoint = cur.fetchone()
        if not checkpoint or checkpoint[0] != str(len(rows)) or len(rows) < 7933:
            raise ProbeError("Staged snapshot and checkpoint disagree")
        parents = Counter(parent for parent, _, panel in rows if panel is None)
        known_series = {series for _, series, panel in rows if panel is not None and series}
        if not parents or len(parents) > 20 or any(
                not isinstance(parent, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", parent)
                for parent in parents):
            raise ProbeError("Missing-panel parent identity changed shape")
        return parents, known_series
    except ProbeError:
        raise
    except Exception:
        raise ProbeError("Could not load private parent identities") from None


def lookup_series(series_id, token, *, requester=request_json):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", series_id):
        raise ProbeError("Invalid series identifier")
    url = BASE + "/content/v2/cms/series/" + quote(series_id, safe="") + "?locale=en-US"
    request = Request(url, headers={"Authorization": "Bearer " + token,
                                    "Accept": "application/json",
                                    "User-Agent": "MarqueeHistoryProbe/1.0"})
    try:
        payload = request_stage(request, "Series catalog lookup", requester=requester)
    except ProbeError as exc:
        if str(exc).endswith("(HTTP 404)"):
            return "not_found"
        raise ProbeError("Series catalog lookup failed") from None
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise ProbeError("Series catalog response changed shape")
    if records[0].get("id") != series_id:
        raise ProbeError("Series catalog returned a different identity")
    return "verified"


def summarize(parents, known_series, token, *, requester=request_json):
    outcomes = {}
    unknown = set(parents) - known_series
    for parent in sorted(parents):
        outcomes[parent] = lookup_series(parent, token, requester=requester)
    counts = Counter(outcomes.values())
    return {"missing_panel_events": sum(parents.values()), "parent_series_ids": len(parents),
            "parents_known_from_episode_panels": len(set(parents) & known_series),
            "events_with_known_parent_series": sum(
                n for parent, n in parents.items() if parent in known_series),
            "catalog_verified_parents": counts["verified"],
            "catalog_not_found_parents": counts["not_found"],
            "unseen_parent_catalog_verified": sum(
                outcomes[parent] == "verified" for parent in unknown),
            "note": "A series catalog match never identifies a missing episode. No records were written."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args(argv)
    try:
        scope = str(UUID(args.user_id))
        parents, known_series = parent_snapshot(os.environ.get("MARQUEE_DATABASE_URL"), scope)
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT"))
        print(json.dumps(summarize(parents, known_series, token), sort_keys=True))
        return 0
    except (ProbeError, ValueError):
        print("Read-only parent catalog probe failed; no private records printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
