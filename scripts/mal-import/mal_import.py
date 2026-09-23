#!/usr/bin/env python3
"""One-time MAL XML status/score seed. No network or database I/O at import time."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from uuid import UUID


MAX_EXPORT_BYTES = 32 * 1024 * 1024
STATUSES = {
    "watching": "watching",
    "completed": "completed",
    "on-hold": "on_hold",
    "on hold": "on_hold",
    "dropped": "dropped",
    "plan to watch": "planned",
    "plan_to_watch": "planned",
}


class ImportErrorMAL(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_export(path):
    # Reject XML DTD/entity expansion; only local XML or XML.gz exports are accepted.
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        data = stream.read(MAX_EXPORT_BYTES + 1)
    if len(data) > MAX_EXPORT_BYTES:
        raise ImportErrorMAL("MAL export exceeds 32 MiB")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ImportErrorMAL("MAL export must not contain a DTD or entities")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportErrorMAL("invalid MAL XML export") from exc
    if root.tag != "myanimelist":
        raise ImportErrorMAL("expected a myanimelist XML root")
    entries = []
    seen = set()
    for node in root:
        if node.tag != "anime":
            continue  # user_info is export metadata; manga is not in scope.
        payload = {child.tag: child.text or "" for child in node}
        identifier = payload.get("series_animedb_id", "").strip()
        if not identifier.isascii() or not identifier.isdigit() or int(identifier) <= 0:
            raise ImportErrorMAL("anime entry is missing a positive MAL ID")
        mal_id = str(int(identifier))
        if mal_id in seen:
            raise ImportErrorMAL(f"duplicate MAL anime ID {mal_id}")
        seen.add(mal_id)
        raw_status = payload.get("my_status", "").strip().lower()
        status = STATUSES.get(raw_status)
        if status is None:
            raise ImportErrorMAL(f"anime {mal_id} has unknown status")
        raw_score = payload.get("my_score", "").strip()
        if not raw_score.isascii() or not raw_score.isdigit() or not 0 <= int(raw_score) <= 10:
            raise ImportErrorMAL(f"anime {mal_id} has invalid score")
        updated = payload.get("my_last_updated", "0").strip()
        if not updated.isascii() or not updated.isdigit():
            raise ImportErrorMAL(f"anime {mal_id} has invalid update timestamp")
        try:
            timestamp = datetime.fromtimestamp(int(updated), timezone.utc) if int(updated) else None
        except (OverflowError, OSError, ValueError) as exc:
            raise ImportErrorMAL(f"anime {mal_id} has invalid update timestamp") from exc
        entries.append({"mal_id": mal_id, "status": status, "score": int(raw_score),
                        "updated_at": timestamp, "payload": payload})
    if not entries:
        raise ImportErrorMAL("MAL export contains no anime entries")
    return entries, hashlib.sha256(data).hexdigest()


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()


def target(cur, mal_id):
    row = one(cur, """select canonical_entity_type, title_id, show_title_id, season_id
        from public.marquee_source_mappings
        where source='mal' and source_entity_type='anime' and source_id=%s""", (mal_id,))
    if row is None:
        return None
    kind, title_id, show_id, season_id = row
    if kind == "season" and season_id:
        check = one(cur, """select t.is_anime from public.marquee_seasons s
            join public.marquee_shows sh on sh.title_id=s.show_title_id
            join public.marquee_titles t on t.id=sh.title_id where s.id=%s""", (season_id,))
        return ("season_id", season_id) if check and check[0] else None
    if kind in ("title", "show"):
        title = title_id if kind == "title" else show_id
        check = one(cur, "select media_type,is_anime from public.marquee_titles where id=%s", (title,))
        return ("title_id", title) if check == ("show", True) else None
    return None


def seed(cur, user_id, entry, column, entity_id):
    """Insert only into empty slots. A MAL import cannot update any existing state."""
    result = {"inserted": 0, "skipped": 0}
    value = (user_id, entity_id, entry["status"], entry["mal_id"], entry["updated_at"])
    cur.execute(f"""insert into public.marquee_statuses
        (user_id,{column},status,source,source_record_id,source_updated_at)
        values (%s,%s,%s,'mal',%s,%s)
        on conflict (user_id,{column}) where {column} is not null do nothing""", value)
    result["inserted" if cur.rowcount else "skipped"] += 1
    if entry["score"]:  # MAL score zero means unrated.
        cur.execute(f"""insert into public.marquee_ratings
            (user_id,{column},score,source,source_record_id,source_updated_at)
            values (%s,%s,%s,'mal',%s,%s)
            on conflict (user_id,{column}) where {column} is not null do nothing""",
            (user_id, entity_id, entry["score"], entry["mal_id"], entry["updated_at"]))
        result["inserted" if cur.rowcount else "skipped"] += 1
    return result


def run(conn, get_export, user_id):
    scope = str(UUID(user_id))
    counts = {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "unmapped": 0}
    with conn.transaction():
        with conn.cursor() as cur:
            run_id = one(cur, """insert into public.marquee_sync_runs (source,user_id,scope_key)
                values ('mal',%s,%s) returning id""", (scope, scope))[0]
    try:
        entries, digest = get_export()
        with conn.transaction():
            with conn.cursor() as cur:
                state = one(cur, """select watermark from public.marquee_sync_state
                    where source='mal' and scope_key=%s for update""", (scope,))
                if state and state[0].get("input_sha256") not in (None, digest):
                    raise ImportErrorMAL("a different MAL export was already seeded; refusing to overwrite")
                for entry in entries:
                    mal_id = entry["mal_id"]
                    counts["fetched"] += 1
                    payload = encoded(entry["payload"])
                    cur.execute("""insert into public.marquee_ingest_raw
                        (source,source_entity_type,source_id,user_id,scope_key,dedupe_key,
                         payload_hash,payload,first_sync_run_id)
                        values ('mal','anime',%s,%s,%s,%s,%s,%s::jsonb,%s)
                        on conflict (scope_key,source,source_entity_type,dedupe_key)
                        do update set last_seen_at=now()""",
                        (mal_id, scope, scope, mal_id, hashlib.sha256(payload.encode()).hexdigest(), payload, run_id))
                    resolved = target(cur, mal_id)
                    if resolved is None:
                        cur.execute("""insert into public.marquee_mapping_review
                            (source,source_entity_type,source_id,source_title,reason)
                            values ('mal','anime',%s,%s,'No verified MAL anime ID mapping to an anime season or show')
                            on conflict (source,source_entity_type,source_id) where status='open'
                            do update set source_title=excluded.source_title,reason=excluded.reason""",
                            (mal_id, entry["payload"].get("series_title")))
                        status = "review"
                        counts["unmapped"] += 1
                    else:
                        column, entity_id = resolved
                        result = seed(cur, scope, entry, column, entity_id)
                        counts["inserted"] += result["inserted"]
                        counts["skipped"] += result["skipped"]
                        cur.execute("""update public.marquee_mapping_review set status='resolved',
                            resolved_at=now(),resolved_mapping_id=(select id from public.marquee_source_mappings
                            where source='mal' and source_entity_type='anime' and source_id=%s),
                            resolution_notes='Resolved by stable MAL ID mapping'
                            where source='mal' and source_entity_type='anime' and source_id=%s and status='open'""",
                            (mal_id, mal_id))
                        status = "mapped"
                    cur.execute("""update public.marquee_ingest_raw set normalization_status=%s,
                        normalization_error=null where scope_key=%s and source='mal'
                        and source_entity_type='anime' and dedupe_key=%s""", (status, scope, mal_id))
                cur.execute("""update public.marquee_sync_runs set status='succeeded',finished_at=now(),
                    fetched_count=%s,inserted_count=%s,updated_count=%s,skipped_count=%s,unmapped_count=%s
                    where id=%s and status='running'""", (*counts.values(), run_id))
                if cur.rowcount != 1:
                    raise ImportErrorMAL("sync run could not finish")
                checkpoint = encoded({"input_sha256": digest, "records": len(entries),
                                      "seeded_from": "mal_xml_export", "completed_at": datetime.now(timezone.utc).isoformat()})
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,watermark,last_attempt_at,last_success_at,last_success_run_id)
                    values ('mal',%s,%s,%s::jsonb,now(),now(),%s)
                    on conflict (source,scope_key) do update set watermark=excluded.watermark,
                    last_attempt_at=now(),last_success_at=now(),last_success_run_id=excluded.last_success_run_id,
                    last_error=null,consecutive_failures=0,updated_at=now()""",
                    (scope, scope, checkpoint, run_id))
        return counts
    except Exception as exc:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""update public.marquee_sync_runs set status='failed',finished_at=now(),
                    error_count=1,error_summary=%s where id=%s and status='running'""", (str(exc)[:500], run_id))
                cur.execute("""insert into public.marquee_sync_state
                    (source,user_id,scope_key,last_attempt_at,last_error,consecutive_failures)
                    values ('mal',%s,%s,now(),%s,1)
                    on conflict (source,scope_key) do update set last_attempt_at=now(),last_error=excluded.last_error,
                    consecutive_failures=public.marquee_sync_state.consecutive_failures+1,updated_at=now()""",
                    (scope, scope, str(exc)[:500]))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Local MAL anime-list XML or XML.gz export")
    parser.add_argument("--user-id", required=True, help="Existing Supabase auth.users UUID")
    parser.add_argument("--dry-run", action="store_true", help="Validate export without a database connection")
    args = parser.parse_args(argv)
    user_id = str(UUID(args.user_id))
    get_export = lambda: load_export(args.input)
    if args.dry_run:
        entries, digest = get_export()
        print(json.dumps({"validated": len(entries), "input_sha256": digest}))
        return 0
    database_url = os.environ.get("MARQUEE_DATABASE_URL")
    if not database_url:
        parser.error("MARQUEE_DATABASE_URL required for import")
    try:
        import psycopg
    except ImportError:
        parser.error("install scripts/trakt-sync/requirements.txt first")
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            locked = one(cur, "select pg_try_advisory_lock(hashtext('marquee.mal'),hashtext(%s))", (user_id,))
            if not locked[0]:
                raise ImportErrorMAL("another MAL import is already active for this user")
        try:
            counts = run(conn, get_export, user_id)
        finally:
            with conn.cursor() as cur:
                cur.execute("select pg_advisory_unlock(hashtext('marquee.mal'),hashtext(%s))", (user_id,))
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ImportErrorMAL, ValueError, OSError) as exc:
        print(f"MAL import failed: {exc}", file=sys.stderr)
        sys.exit(1)
