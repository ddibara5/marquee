-- psql integration probe. RUN ONLY IN AN ISOLATED TEST DATABASE after applying
-- the migration there. Requires two existing disposable auth.users IDs.
-- Example: psql -v owner_uuid=<uuid> -v other_uuid=<uuid> -f this_file.sql
-- Everything here is wrapped in a rollback, including the sample records.
\set ON_ERROR_STOP on
begin;

select 1 / case when count(*) = 2 then 1 else 0 end as two_users_required
from auth.users where id in (:'owner_uuid'::uuid, :'other_uuid'::uuid);

insert into public.marquee_titles (media_type, display_title)
values ('show', 'Marquee disposable verification show')
returning id as title_id \gset

select 1 / case when not has_table_privilege('anon', 'public.marquee_statuses', 'select')
                   and not has_table_privilege('anon', 'public.marquee_ingest_raw', 'insert')
              then 1 else 0 end as anon_denied;

set local role authenticated;
select set_config('request.jwt.claim.sub', :'owner_uuid', true);
insert into public.marquee_statuses (user_id, title_id, status, source)
values (:'owner_uuid'::uuid, :'title_id'::uuid, 'watching', 'manual')
returning id as status_id \gset

select 1 / case when count(*) = 1 then 1 else 0 end as owner_reads_own
from public.marquee_statuses where id = :'status_id'::uuid;

select set_config('marquee.test.other_uuid', :'other_uuid', true);
select set_config('marquee.test.title_id', :'title_id', true);
do $$ begin
  begin
    insert into public.marquee_statuses (user_id, title_id, status, source)
    values (current_setting('marquee.test.other_uuid')::uuid,
            current_setting('marquee.test.title_id')::uuid, 'watching', 'manual');
    raise exception 'cross-owner insert was unexpectedly allowed';
  exception when insufficient_privilege then null;
  end;
end $$;

select set_config('request.jwt.claim.sub', :'other_uuid', true);
select 1 / case when count(*) = 0 then 1 else 0 end as other_cannot_read_owner
from public.marquee_statuses where id = :'status_id'::uuid;

with forbidden_update as (
  update public.marquee_statuses set status = 'completed'
  where id = :'status_id'::uuid returning id
)
select 1 / case when count(*) = 0 then 1 else 0 end as other_cannot_update_owner
from forbidden_update;

reset role;
set local role service_role;
insert into public.marquee_source_mappings (
  source, source_entity_type, source_id, canonical_entity_type, title_id, match_method
) values ('anilist', 'media', 'marquee-verification-id', 'title', :'title_id'::uuid, 'external_id');
insert into public.marquee_source_mappings (
  source, source_entity_type, source_id, canonical_entity_type, title_id, match_method
) values ('anilist', 'media', 'marquee-verification-id', 'title', :'title_id'::uuid, 'external_id')
on conflict (source, source_entity_type, source_id) do nothing;
select 1 / case when count(*) = 1 then 1 else 0 end as replay_is_idempotent
from public.marquee_source_mappings
where source = 'anilist' and source_entity_type = 'media' and source_id = 'marquee-verification-id';

reset role;
rollback;
