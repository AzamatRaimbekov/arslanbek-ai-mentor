-- Aggregate complete datasets on the server, independently of PostgREST row limits.
-- No new collection: all statistics use the existing consent-based telemetry.
create index if not exists students_last_seen_idx on public.students (last_seen desc);
create index if not exists students_group_name_idx on public.students (group_name);

-- Explicit privileges also work in projects without Supabase's default grants.
revoke all on public.students, public.prompts, public.summaries, public.admins from anon;
grant select on public.students, public.prompts, public.summaries, public.admins to authenticated;

create or replace function public.dashboard_stats(p_days integer default 30)
returns jsonb
language plpgsql stable security invoker set search_path = public as $$
declare
  v_start timestamptz;
  v_result jsonb;
begin
  if not public.is_admin() then
    raise exception 'Administrator access required' using errcode = '42501';
  end if;
  if p_days not in (14, 30, 90) then
    raise exception 'Period must be 14, 30 or 90 days' using errcode = '22023';
  end if;
  v_start := ((now() at time zone 'UTC')::date - (p_days - 1))::timestamp at time zone 'UTC';
  select jsonb_build_object(
    'students', (select count(*) from public.students),
    'new_students', (select count(*) from public.students where first_seen >= v_start),
    'active_students', (select count(*) from public.students where last_seen >= v_start),
    'prompts', (select count(*) from public.prompts where created_at >= v_start),
    'summaries', (select count(*) from public.summaries where created_at >= v_start),
    'average_level', (select round(avg(level)::numeric, 1) from public.students),
    'unassessed', (select count(*) from public.students where level is null),
    'groups', coalesce((select jsonb_agg(g order by g) from (
      select distinct group_name as g from public.students where nullif(group_name, '') is not null
    ) groups), '[]'::jsonb),
    'levels', (select jsonb_agg(jsonb_build_object('level', l, 'count', n) order by l) from (
      select l, count(s.id) as n from generate_series(0, 5) l
      left join public.students s on s.level = l group by l
    ) distribution),
    'activity', (select jsonb_agg(jsonb_build_object('date', d::date, 'prompts', coalesce(n, 0)) order by d) from (
      select (v_start at time zone 'UTC')::date + offset_day as d
      from generate_series(0, p_days - 1) offset_day
    ) dates left join (
      select (created_at at time zone 'UTC')::date as day, count(*) as n
      from public.prompts where created_at >= v_start group by day
    ) counts on counts.day = dates.d)
  ) into v_result;
  return v_result;
end;
$$;
revoke all on function public.dashboard_stats(integer) from public;
grant execute on function public.dashboard_stats(integer) to authenticated;
