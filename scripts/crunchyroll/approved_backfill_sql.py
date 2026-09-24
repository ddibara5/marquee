"""Render the reviewed, idempotent Marquee historical-completion replay SQL.

Only execute after the 7,933-row source snapshot, manifest and row-level
preflight agree. No connection strings or user IDs are embedded in this file.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "approved_media_manifest.json").read_text())
MANUAL_TOTALS = {
    205: 26, 1535: 37, 1575: 25, 4087: 22, 4898: 24,
    5114: 64, 9253: 24, 9919: 25, 11061: 148, 11757: 25,
    16498: 25, 20605: 12, 20729: 73, 20850: 12, 21355: 25,
    21459: 13, 97940: 170, 101348: 24, 101922: 26, 105333: 24,
    113415: 24, 126403: 11, 127230: 12, 137822: 24, 140960: 12,
    151807: 12, 153288: 12, 154587: 28, 155418: 12, 178754: 11,
}
MANUAL_FILMS = {199, 20954, 178788}


def quoted(value):
    return "'" + value.replace("'", "''") + "'"


def manifest_cte():
    data = quoted(json.dumps(MANIFEST, ensure_ascii=False))
    return (f"manifest as (select * from jsonb_to_recordset({data}::jsonb) as x("
            "media_id int, series_id text, show_anchor_media_id int,"
            "new_show_name text, label text, total int, kind text, season_number int))")


def candidates_cte():
    bulk = (HERE / "bulk_identity_proposal.sql").read_text().strip().rstrip(";")
    extra = (HERE / "additional_identity_proposal.sql").read_text().strip().rstrip(";")
    return (
        f"bulk as ({bulk}), extra as ({extra}), candidates as ("
        "select source_identifier, series_id, anilist_media_id,"
        " local_episode_number, target_kind from bulk"
        " where complete and identity_consistent"
        " and scope in ('main','confirmed_other','selected_special')"
        " union all select source_identifier, series_id, anilist_media_id,"
        " local_episode_number, 'episode'::text from extra"
        " where complete and identity_consistent and scope='episode_candidate')")


def manual_cte():
    values = ",".join(f"({k},{v})" for k, v in sorted(MANUAL_TOTALS.items()))
    return (f"verified_manual(media_id,total) as (values {values}),"
            "manual_rows as (select r.id raw_id,r.user_id,"
            " (r.payload->>'mediaId')::int media_id,"
            " (r.payload->>'progress')::int progress"
            " from public.marquee_ingest_raw r"
            " where r.source='anilist' and r.source_entity_type='media_list'"
            " and r.payload->>'status'='COMPLETED'),"
            "manual_full as (select r.raw_id,r.user_id,r.media_id,v.total"
            " from manual_rows r join verified_manual v using(media_id)"
            " where r.progress=v.total)")


def with_(fragment, sql):
    return f"with {fragment} {sql.strip()};"


def guard(condition, message):
    return ("do $$ begin if " + condition + " then raise exception " +
            quoted(message) + "; end if; end $$;")


def catalog_sql():
    m = manifest_cte()
    statements = [
        "begin;",
        guard("(select count(*) from public.marquee_ingest_raw where source='crunchyroll' and source_entity_type='history_event') <> 7933",
              "Crunchyroll raw snapshot changed"),
        guard("(select count(*) from public.game_ranks) <> 53 or (select count(*) from public.rank_comparisons) <> 154",
              "GameDeck regression baseline changed"),
        guard("(select count(*) from public.marquee_source_mappings where source='anilist' and source_entity_type='media') not in (50,101)",
              "AniList catalog changed; review before replay"),
        with_(m, "insert into public.marquee_titles(media_type,display_title,is_anime)"
              " select distinct 'show',new_show_name,true from manifest x"
              " where new_show_name is not null and not exists"
              " (select 1 from public.marquee_titles t where t.display_title=x.new_show_name)"),
        with_(m, "insert into public.marquee_shows(title_id)"
              " select distinct t.id from manifest x join public.marquee_titles t"
              " on t.display_title=x.new_show_name and t.media_type='show'"
              " where x.new_show_name is not null on conflict do nothing"),
        with_(m, "insert into public.marquee_titles(media_type,display_title,is_anime)"
              " select 'movie',label,true from manifest x where kind='movie'"
              " and not exists(select 1 from public.marquee_titles t"
              " where t.display_title=x.label and t.media_type='movie')"),
        with_(m, "insert into public.marquee_movies(title_id)"
              " select t.id from manifest x join public.marquee_titles t"
              " on t.display_title=x.label and t.media_type='movie'"
              " where x.kind='movie' on conflict do nothing"),
        # The imported 170166 entry is the later Bridon Arc; its season number
        # had been assigned 2 before the 2023 season (136484) was identified.
        "update public.marquee_seasons s set season_number=3,"
        " display_title='Bridon Arc' from public.marquee_source_mappings a"
        " where a.source='anilist' and a.source_entity_type='media'"
        " and a.source_id='170166' and a.season_id=s.id"
        " and s.season_number=2;",
        with_(m, "insert into public.marquee_seasons(show_title_id,season_number,display_title)"
              " select coalesce(anchor_s.show_title_id,t.id),x.season_number,x.label"
              " from manifest x left join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=x.show_anchor_media_id::text"
              " left join public.marquee_seasons anchor_s on anchor_s.id=a.season_id"
              " left join public.marquee_titles t on t.display_title=x.new_show_name"
              " and t.media_type='show'"
              " where x.kind='season' and not exists"
              " (select 1 from public.marquee_source_mappings old"
              " where old.source='anilist' and old.source_entity_type='media'"
              " and old.source_id=x.media_id::text)"
              " and not exists(select 1 from public.marquee_seasons prior"
              " where prior.show_title_id=coalesce(anchor_s.show_title_id,t.id)"
              " and prior.display_title=x.label)"),
        with_(m, "insert into public.marquee_source_mappings"
              "(source,source_entity_type,source_id,canonical_entity_type,"
              "season_id,movie_title_id,match_method,manual_locked,notes)"
              " select 'anilist','media',x.media_id::text,x.kind,"
              " case when x.kind='season' then s.id end,"
              " case when x.kind='movie' then t_movie.id end,"
              " 'manual',true,'Reviewed AniList catalog identity; no user-list entry implied'"
              " from manifest x left join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=x.show_anchor_media_id::text"
              " left join public.marquee_seasons anchor_s on anchor_s.id=a.season_id"
              " left join public.marquee_titles t on t.display_title=x.new_show_name"
              " and t.media_type='show'"
              " left join public.marquee_seasons s"
              " on s.show_title_id=coalesce(anchor_s.show_title_id,t.id)"
              " and s.display_title=x.label"
              " left join public.marquee_titles t_movie"
              " on t_movie.display_title=x.label and t_movie.media_type='movie'"
              " where not exists(select 1 from public.marquee_source_mappings old"
              " where old.source='anilist' and old.source_entity_type='media'"
              " and old.source_id=x.media_id::text)"),
        "insert into public.marquee_seasons(show_title_id,display_title)"
        " select s.show_title_id,'Link Click 5.5'"
        " from public.marquee_source_mappings a"
        " join public.marquee_seasons s on s.id=a.season_id"
        " where a.source='anilist' and a.source_entity_type='media'"
        " and a.source_id='126403' and not exists"
        " (select 1 from public.marquee_seasons p"
        " where p.show_title_id=s.show_title_id"
        " and p.display_title='Link Click 5.5');",
        guard("(select count(*) from public.marquee_source_mappings where source='anilist' and source_entity_type='media') <> 101",
              "Expected 51 new AniList catalog media mappings"),
        "commit;",
    ]
    return "\n".join(statements)


def replay_sql(phase="replay"):
    c, m, v = candidates_cte(), manifest_cte(), manual_cte()
    # De-duplication happens on the canonical target, never timestamp/version.
    statements = [
        "begin;",
        guard("(select count(*) from public.marquee_ingest_raw where source='crunchyroll' and source_entity_type='history_event') <> 7933",
              "Crunchyroll raw snapshot changed"),
        guard("(select count(*) from public.game_ranks) <> 53 or (select count(*) from public.rank_comparisons) <> 154",
              "GameDeck regression baseline changed"),
        with_(c, "select count(*) from candidates"),  # cheap planner smoke check
        with_(c, "insert into public.marquee_episodes(season_id,episode_number)"
              " select distinct a.season_id,coalesce(c.local_episode_number,1)"
              " from candidates c join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=c.anilist_media_id::text"
              " where a.season_id is not null"
              " on conflict do nothing"),
        # The user selected this special separately, not regular episode six.
        "insert into public.marquee_episodes(season_id,episode_number)"
        " select s.id,1 from public.marquee_seasons s"
        " where s.display_title='Link Click 5.5'"
        " on conflict do nothing;",
        with_(v, "insert into public.marquee_episodes(season_id,episode_number)"
              " select distinct a.season_id,n from manual_full r"
              " join public.marquee_source_mappings a on a.source='anilist'"
              " and a.source_entity_type='media' and a.source_id=r.media_id::text"
              " cross join lateral generate_series(1,r.total) n"
              " on conflict do nothing"),
        with_(c, "insert into public.marquee_source_mappings"
              "(source,source_entity_type,source_id,canonical_entity_type,"
              "episode_id,movie_title_id,match_method,manual_locked,notes)"
              " select 'crunchyroll','episode',c.source_identifier,"
              " case when c.target_kind='movie' then 'movie' else 'episode' end,"
              " case when c.target_kind<>'movie' then ep.id end,"
              " case when c.target_kind='movie' then a.movie_title_id end,"
              " 'manual',true,'Reviewed stable source identifier; date unverified'"
              " from candidates c left join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=c.anilist_media_id::text"
              " left join public.marquee_seasons special"
              " on special.display_title='Link Click 5.5'"
              " and special.show_title_id=(select s.show_title_id"
              " from public.marquee_source_mappings lm"
              " join public.marquee_seasons s on s.id=lm.season_id"
              " where lm.source='anilist' and lm.source_entity_type='media'"
              " and lm.source_id='126403')"
              " left join public.marquee_episodes ep"
              " on ep.season_id=coalesce(a.season_id,special.id)"
              " and ep.episode_number=coalesce(c.local_episode_number,1)"
              " where not exists(select 1 from public.marquee_source_mappings prior"
              " where prior.source='crunchyroll' and prior.source_entity_type='episode'"
              " and prior.source_id=c.source_identifier)"),
        guard("(select count(*) from public.marquee_source_mappings where source='crunchyroll' and source_entity_type='episode') <> 1487",
              "Crunchyroll episode/movie mapping count mismatch"),
        with_(c, "insert into public.marquee_undated_completions(user_id,episode_id,movie_title_id)"
              " select distinct r.user_id,cm.episode_id,cm.movie_title_id"
              " from candidates c join public.marquee_source_mappings cm"
              " on cm.source='crunchyroll' and cm.source_entity_type='episode'"
              " and cm.source_id=c.source_identifier"
              " join public.marquee_ingest_raw r"
              " on r.source='crunchyroll' and r.source_entity_type='history_event'"
              " and r.payload#>>'{panel,episode_metadata,identifier}'=c.source_identifier"
              " and r.payload->>'fully_watched'='true'"
              " on conflict do nothing"),
        with_(v, "insert into public.marquee_undated_completions(user_id,episode_id)"
              " select distinct r.user_id,e.id from manual_full r"
              " join public.marquee_source_mappings a on a.source='anilist'"
              " and a.source_entity_type='media' and a.source_id=r.media_id::text"
              " join public.marquee_episodes e on e.season_id=a.season_id"
              " and e.episode_number between 1 and r.total"
              " on conflict do nothing"),
        with_(v, "insert into public.marquee_undated_completions(user_id,movie_title_id)"
              " select distinct r.user_id,a.movie_title_id from manual_rows r"
              " join public.marquee_source_mappings a on a.source='anilist'"
              " and a.source_entity_type='media' and a.source_id=r.media_id::text"
              " where r.media_id in (199,20954,178788)"
              " and r.progress=1 and a.movie_title_id is not null"
              " on conflict do nothing"),
        guard("(select count(*) from public.marquee_undated_completions) <> 1664",
              "Undated canonical target count mismatch"),
        "insert into public.marquee_undated_completion_evidence"
        "(user_id,completion_id,raw_id,source,source_episode_identifier)"
        " select r.user_id,u.id,r.id,'crunchyroll',cm.source_id"
        " from public.marquee_ingest_raw r"
        " join public.marquee_source_mappings cm"
        " on cm.source='crunchyroll' and cm.source_entity_type='episode'"
        " and cm.source_id=r.payload#>>'{panel,episode_metadata,identifier}'"
        " join public.marquee_undated_completions u"
        " on u.user_id=r.user_id and"
        " ((cm.episode_id is not null and u.episode_id=cm.episode_id)"
        " or (cm.movie_title_id is not null and u.movie_title_id=cm.movie_title_id))"
        " where r.source='crunchyroll' and r.source_entity_type='history_event'"
        " and r.payload->>'fully_watched'='true'"
        " and r.payload->>'parent_id' not in ('GRMG8ZQZR','G6DQDD3WR')"
        " and r.payload#>>'{panel,episode_metadata,series_id}'"
        " not in ('GRMG8ZQZR','G6DQDD3WR')"
        " on conflict do nothing;",
        with_(v, "insert into public.marquee_undated_completion_evidence"
              "(user_id,completion_id,raw_id,source)"
              " select r.user_id,u.id,r.raw_id,'anilist' from manual_full r"
              " join public.marquee_source_mappings a on a.source='anilist'"
              " and a.source_entity_type='media' and a.source_id=r.media_id::text"
              " join public.marquee_episodes e on e.season_id=a.season_id"
              " and e.episode_number between 1 and r.total"
              " join public.marquee_undated_completions u"
              " on u.user_id=r.user_id and u.episode_id=e.id"
              " on conflict do nothing"),
        with_(v, "insert into public.marquee_undated_completion_evidence"
              "(user_id,completion_id,raw_id,source)"
              " select r.user_id,u.id,r.raw_id,'anilist' from manual_rows r"
              " join public.marquee_source_mappings a on a.source='anilist'"
              " and a.source_entity_type='media' and a.source_id=r.media_id::text"
              " join public.marquee_undated_completions u"
              " on u.user_id=r.user_id and u.movie_title_id=a.movie_title_id"
              " where r.media_id in (199,20954,178788) and r.progress=1"
              " on conflict do nothing"),
        guard("(select count(*) from public.marquee_undated_completion_evidence where source='crunchyroll') <> 3007"
              " or (select count(*) from public.marquee_undated_completion_evidence where source='anilist') <> 985",
              "Undated raw evidence count mismatch"),
        # Existing AniList raw entries remain untouched. Only Marquee's
        # effective status changes; a manual lock always wins.
        with_(m, "insert into public.marquee_statuses(user_id,season_id,status,source)"
              " select owner.user_id,a.season_id,'completed','crunchyroll'"
              " from manifest x join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=x.media_id::text and a.season_id is not null"
              " cross join (select distinct user_id from public.marquee_ingest_raw"
              " where source='crunchyroll' and source_entity_type='history_event') owner"
              " where (select count(*) from public.marquee_episodes ep"
              " join public.marquee_undated_completions u on u.episode_id=ep.id"
              " and u.user_id=owner.user_id"
              " where ep.season_id=a.season_id)=x.total"
              " and not exists(select 1 from public.marquee_statuses s"
              " where s.user_id=owner.user_id and s.season_id=a.season_id)"
              " on conflict do nothing"),
        with_(m, "update public.marquee_statuses s set status='completed',"
              " source='crunchyroll',source_record_id=null,updated_at=now()"
              " from manifest x join public.marquee_source_mappings a"
              " on a.source='anilist' and a.source_entity_type='media'"
              " and a.source_id=x.media_id::text"
              " where s.season_id=a.season_id and s.status<>'completed'"
              " and not s.manual_locked and"
              " (select count(*) from public.marquee_episodes ep"
              " join public.marquee_undated_completions u on u.episode_id=ep.id"
              " and u.user_id=s.user_id"
              " where ep.season_id=a.season_id)=x.total"),
        "commit;",
    ]
    if phase == "replay":
        return "\n".join(statements)
    steps = {
        "episodes": [3, 4, 5, 6],
        "mappings": [7, 8],
        "completions": [9, 10, 11, 12],
        "evidence": [13, 14, 15, 16],
        "status": [17, 18],
    }
    return "\n".join([statements[0], statements[1], statements[2]]
                     + [statements[i] for i in steps[phase]] + [statements[-1]])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("catalog", "replay", "episodes",
                                     "mappings", "completions", "evidence",
                                     "status"))
    args = p.parse_args()
    assert len(MANIFEST) == 81
    assert len({x["media_id"] for x in MANIFEST}) == 81
    assert len(MANUAL_TOTALS) == 30
    print(catalog_sql() if args.phase == "catalog" else replay_sql(args.phase))


if __name__ == "__main__":
    main()
