#!/usr/bin/env python3
"""Stage complete Crunchyroll history for private review; never create watches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from uuid import UUID

from history_probe import ProbeError, bearer_from_cookie, get_account_id, legacy_history_pages
from import_gate import inspect, database_counts


class StageError(RuntimeError):
    pass


def observations(pages):
    """Yield stable raw keys and review identities, retaining missing data."""
    for page in pages:
        for item in page:
            panel = item.get("panel")
            metadata = panel.get("episode_metadata") if isinstance(panel, dict) else None
            if not isinstance(panel, dict) or not isinstance(panel.get("id"), str) or not panel["id"]:
                review = ("history_event", item["id"], "Episode panel unavailable")
            elif not isinstance(metadata, dict) or not all(
                isinstance(metadata.get(key), str) and metadata[key]
                for key in ("series_id", "season_id")
            ):
                review = ("episode", panel["id"], "Source series or season identifier unavailable")
            else:
                review = ("season", metadata["season_id"], "Verify source season, version and AniList relation")
                number = metadata.get("episode_number")
                if not ((type(number) is int and number > 0) or
                        (isinstance(number, str) and number.isdecimal() and int(number) > 0)):
                    yield item, (review, ("episode", panel["id"], "Episode number unavailable"))
                    continue
            yield item, (review,)


def stage(conn, user_id, pages, account_id):
    """One atomic transaction: raw observations, reviews, run and checkpoint."""
    scope = str(UUID(user_id))
    account_digest = hashlib.sha256(account_id.encode()).hexdigest()
    flattened = list(observations(pages))
    if not flattened:
        raise StageError("No complete history to stage")
    staged = updated = reviewed = 0
    incoming_ids = {item["id"] for item, _ in flattened}
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtext(%s))", ("marquee:crunchyroll:" + scope,))
            cur.execute("""select watermark->>'account_digest' from public.marquee_sync_state
                where source='crunchyroll' and scope_key=%s""", (scope,))
            old = cur.fetchone()
            if old and old[0] and old[0] != account_digest:
                raise StageError("Source account changed since the last successful stage")
            cur.execute("""select dedupe_key from public.marquee_ingest_raw
                where scope_key=%s and source='crunchyroll' and source_entity_type='history_event'""", (scope,))
            existing_ids = {row[0] for row in cur.fetchall()}
            if existing_ids and (not old or not old[0]):
                raise StageError("Existing raw history has no verified source-account checkpoint")
            if not existing_ids <= incoming_ids:
                raise StageError("Previously staged event is absent from the complete feed")
            cur.execute("""select count(*) from public.marquee_source_mappings
                where source='crunchyroll'""")
            if cur.fetchone()[0]:
                raise StageError("Reviewed mappings exist; raw-only staging must not reopen reviews")
            cur.execute("""select count(*) from public.marquee_watch_history_sources
                where user_id=%s and source='crunchyroll'""", (scope,))
            if cur.fetchone()[0]:
                raise StageError("Canonical Crunchyroll watches exist; use a reviewed replay worker")
            cur.execute("""insert into public.marquee_sync_runs (source,user_id,scope_key)
                values ('crunchyroll',%s,%s) returning id""", (scope, scope))
            run_id = cur.fetchone()[0]
            for item, reviews in flattened:
                event_id = item["id"]
                cur.execute("""select payload->>'date_played',payload #>> '{panel,id}'
                    from public.marquee_ingest_raw
                    where scope_key=%s and source='crunchyroll'
                    and source_entity_type='history_event' and dedupe_key=%s""", (scope, event_id))
                prior = cur.fetchone()
                panel = item.get("panel")
                panel_id = panel.get("id") if isinstance(panel, dict) else None
                if prior and (prior[0] != item["date_played"] or
                              (prior[1] and panel_id and prior[1] != panel_id)):
                    raise StageError("Existing source event identity changed; no records committed")
                encoded = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                digest = hashlib.sha256(encoded.encode()).hexdigest()
                cur.execute("""insert into public.marquee_ingest_raw
                    (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,
                     payload_hash,payload,first_sync_run_id,normalization_status)
                    values ('crunchyroll','history_event',%s,%s,%s,%s,%s,%s::jsonb,%s,'review')
                    on conflict (scope_key,source,source_entity_type,dedupe_key)
                    do update set payload_hash=excluded.payload_hash,payload=excluded.payload,
                                  last_seen_at=now(),normalization_status='review'""",
                    (event_id, scope, scope, event_id, digest, encoded, run_id))
                if prior:
                    updated += 1
                else:
                    staged += 1
                for review in reviews:
                    cur.execute("""insert into public.marquee_mapping_review
                        (source,source_entity_type,source_id,reason)
                        values ('crunchyroll',%s,%s,%s)
                        on conflict (source,source_entity_type,source_id) where status='open'
                        do nothing""", review)
                    reviewed += cur.rowcount
            cur.execute("""update public.marquee_sync_runs set status='succeeded',finished_at=now(),
                fetched_count=%s,inserted_count=%s,skipped_count=%s,unmapped_count=%s
                where id=%s and status='running'""",
                (len(flattened), staged, updated, len(flattened), run_id))
            if cur.rowcount != 1:
                raise StageError("Run status could not be finalized")
            watermark = json.dumps({"account_digest": account_digest,
                                    "complete_event_count": len(flattened),
                                    "oldest_event_date": min(item["date_played"] for item, _ in flattened)})
            cur.execute("""insert into public.marquee_sync_state
                (source,user_id,scope_key,watermark,last_attempt_at,last_success_at,last_success_run_id)
                values ('crunchyroll',%s,%s,%s::jsonb,now(),now(),%s)
                on conflict (source,scope_key) do update set watermark=excluded.watermark,
                    last_attempt_at=now(),last_success_at=now(),last_success_run_id=excluded.last_success_run_id,
                    last_error=null,consecutive_failures=0,updated_at=now()""",
                (scope, scope, watermark, run_id))
    return {"events_inserted": staged, "events_replayed": updated, "new_review_groups": reviewed,
            "canonical_watches_created": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--stage", action="store_true", help="Explicitly permit raw-only database writes")
    args = parser.parse_args(argv)
    try:
        user_id = str(UUID(args.user_id))
        token = bearer_from_cookie(os.environ.get("CRUNCHYROLL_ETP_RT", ""))
        account_id, _ = get_account_id(token)
        pages = list(legacy_history_pages(account_id, token))
        coverage = inspect(pages)
        coverage["database"] = database_counts(os.environ.get("MARQUEE_DATABASE_URL"))
        if not args.stage:
            print(json.dumps(coverage, sort_keys=True))
            return 0
        if coverage["database"]["crunchyroll_source_links"]:
            raise StageError("Canonical Crunchyroll watches already exist; use a reviewed replay worker")
        import psycopg
        with psycopg.connect(os.environ["MARQUEE_DATABASE_URL"], connect_timeout=15) as conn:
            result = stage(conn, user_id, pages, account_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ProbeError, StageError, ValueError, KeyError):
        print("Crunchyroll staging failed; no private source records printed", file=sys.stderr)
        return 1
    except Exception:
        print("Crunchyroll staging failed; check connection and transaction, no private records printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
