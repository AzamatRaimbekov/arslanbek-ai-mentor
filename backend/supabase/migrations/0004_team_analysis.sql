create table public.team_reports (
  id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  days integer not null check(days in (14,30,90)),
  group_name text,
  status text not null default 'running' check(status in ('running','complete','failed','insufficient_data')),
  model text,
  prompt_version text,
  input_snapshot jsonb not null,
  report jsonb,
  error text,
  usage jsonb
);
create index team_reports_created_idx on public.team_reports(created_at desc);
alter table public.team_reports enable row level security;
create policy admin_read on public.team_reports for select to authenticated using(public.is_admin());
revoke all on public.team_reports from anon, authenticated;
grant select on public.team_reports to authenticated;
grant all on public.team_reports to service_role;

-- All counts are exact. Text is an explicit stratified sample, not a full transcript.
create function public.team_analysis_snapshot(p_days integer default 30, p_group text default null)
returns jsonb language plpgsql stable security invoker set search_path = public as $$
declare
  v_start timestamptz;
  v_students jsonb;
  v_total integer;
  v_eligible integer;
begin
  if not public.is_admin() then
    raise exception 'Administrator access required' using errcode='42501';
  end if;
  if p_days is null or p_days not in (14,30,90) then
    raise exception 'Period must be 14, 30 or 90 days' using errcode='22023';
  end if;
  v_start := ((now() at time zone 'UTC')::date - (p_days - 1))::timestamp at time zone 'UTC';
  select count(*), count(*) filter(where analysis_allowed) into v_total,v_eligible
  from public.students where p_group is null or group_name = p_group;
  if v_eligible > 50 then
    raise exception 'More than 50 eligible devices: select a smaller group' using errcode='22023';
  end if;

  select coalesce(jsonb_agg(jsonb_build_object(
    'student_id', s.id,
    'display_name', coalesce(nullif(s.display_name,''),nullif(s.claude_name,''),nullif(s.git_name,''),'Без имени'),
    'group_name', s.group_name,
    'metrics', jsonb_build_object(
      'ref', 'metrics:' || s.id,
      'prompts', (select count(*) from public.prompts p where p.student_id=s.id and p.created_at between v_start and now()),
      'sessions', (select count(distinct nullif(p.session_id,'')) from public.prompts p where p.student_id=s.id and p.created_at between v_start and now()),
      'projects', (select count(distinct nullif(p.project,'')) from public.prompts p where p.student_id=s.id and p.created_at between v_start and now()),
      'active_days', (select count(distinct (p.created_at at time zone 'UTC')::date) from public.prompts p where p.student_id=s.id and p.created_at between v_start and now()),
      'summaries', (select count(*) from public.summaries x where x.student_id=s.id and x.created_at between v_start and now())
    ),
    'prompts', coalesce((select jsonb_agg(jsonb_build_object(
      'ref', 'prompt:'||p.id, 'created_at',p.created_at,'text',left(p.prompt,1600),
      'truncated',length(p.prompt)>1600,'project',p.project,'session_id',p.session_id,
      'source_type','student_prompt') order by p.created_at,p.id)
      from (
        select distinct on(bucket) * from (
          select p.*,ntile(8) over(order by created_at,id) as bucket
          from public.prompts p where p.student_id=s.id and p.created_at between v_start and now()
        ) bucketed order by bucket,created_at desc,id desc
      ) p), '[]'::jsonb),
    'summaries', coalesce((select jsonb_agg(jsonb_build_object(
      'ref','summary:'||x.id,'created_at',x.created_at,'level',x.level,
      'stage',x.stage,'summary',left(x.summary,1600),'strengths',left(x.strengths,800),
      'struggles',left(x.struggles,800),'next_step',left(x.next_step,800),
      'truncated',coalesce(length(x.summary)>1600 or length(x.strengths)>800 or length(x.struggles)>800 or length(x.next_step)>800,false),
      'source_type','mentor_assessment') order by x.created_at,x.id)
      from (
        select distinct on(bucket) * from (
          select x.*,ntile(5) over(order by created_at,id) as bucket
          from public.summaries x where x.student_id=s.id and x.created_at between v_start and now()
        ) bucketed order by bucket,created_at desc,id desc
      ) x), '[]'::jsonb)
  ) order by s.id),'[]'::jsonb) into v_students
  from public.students s where s.analysis_allowed and (p_group is null or s.group_name=p_group);

  return jsonb_build_object('snapshot_at',now(),'period_start',v_start,'period_end',now(),
    'days',p_days,'group_name',p_group,'total_devices',v_total,'eligible_devices',v_eligible,
    'excluded_without_analysis_consent',v_total-v_eligible,'students',v_students,
    'sampling','Up to 8 prompts and 5 mentor assessments per device, spread across chronological buckets. Text may be truncated. Counts are exact. Devices are not unique people.');
end;
$$;
revoke all on function public.team_analysis_snapshot(integer,text) from public;
grant execute on function public.team_analysis_snapshot(integer,text) to authenticated;

-- One request per admin every two minutes, including simultaneous requests.
create function public.begin_team_analysis(p_days integer default 30,p_group text default null)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_snapshot jsonb; v_report public.team_reports%rowtype;
begin
  if not public.is_admin() then
    raise exception 'Administrator access required' using errcode='42501';
  end if;
  perform pg_advisory_xact_lock(hashtext('team-analysis:'||auth.uid()::text));
  if exists(select 1 from public.team_reports where created_by=auth.uid() and created_at>now()-interval '2 minutes') then
    raise exception 'Wait two minutes before requesting another analysis' using errcode='P0001';
  end if;
  v_snapshot := public.team_analysis_snapshot(p_days,p_group);
  if octet_length(v_snapshot::text)>600000 then
    raise exception 'Analysis input is too large: select a smaller group' using errcode='22023';
  end if;
  insert into public.team_reports(created_by,days,group_name,input_snapshot)
    values(auth.uid(),p_days,p_group,v_snapshot) returning * into v_report;
  return jsonb_build_object('id',v_report.id,'input_snapshot',v_report.input_snapshot);
end;
$$;
revoke all on function public.begin_team_analysis(integer,text) from public;
grant execute on function public.begin_team_analysis(integer,text) to authenticated;
