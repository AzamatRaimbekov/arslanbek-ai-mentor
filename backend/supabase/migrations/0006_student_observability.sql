-- Add observations without rewriting applied migrations or rejecting v1 clients.
alter table public.prompts add column observability jsonb;
alter table public.students add column environment jsonb;
alter table public.students add column environment_updated_at timestamptz;

create table public.tool_events (
  id bigint generated always as identity primary key,
  student_id uuid not null references public.students(id) on delete cascade,
  event_id uuid, summary_id bigint references public.summaries(id) on delete cascade,
  session_id text, project text, client text not null,
  kind text not null check (kind in ('skill','plugin','mcp','harness','tool')),
  tool_id text not null, action text not null check (action in ('used','created','configured')),
  actor text not null check (actor in ('learner','agent','together','unknown')),
  source text not null check (source in ('tool_hook','mentor_report')),
  evidence text, created_at timestamptz not null default now(),
  unique(student_id,event_id), unique(summary_id,kind,tool_id,action)
);
create index tool_events_student_time on public.tool_events(student_id,created_at desc);
create table public.security_alerts (
  id bigint generated always as identity primary key,
  student_id uuid not null references public.students(id) on delete cascade,
  prompt_id bigint references public.prompts(id) on delete cascade,
  tool_event_id bigint references public.tool_events(id) on delete cascade,
  category text not null check (category in ('api_key','private_key','credential','financial_id','confidential_marker')),
  severity text not null check (severity in ('warning','critical')),
  occurrences integer not null check (occurrences between 1 and 100),
  status text not null default 'open' check (status in ('open','reviewed','false_positive')),
  created_at timestamptz not null default now(), reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id), unique(prompt_id,category), unique(tool_event_id,category),
  check ((prompt_id is null) <> (tool_event_id is null))
);
create index security_alerts_status_time on public.security_alerts(status,created_at desc);
create index prompts_observability_tags on public.prompts using gin(observability jsonb_path_ops);
alter table public.tool_events enable row level security;
alter table public.security_alerts enable row level security;
create policy admin_read on public.tool_events for select to authenticated using(public.is_admin());
create policy admin_read on public.security_alerts for select to authenticated using(public.is_admin());
revoke all on public.tool_events, public.security_alerts from public,anon,authenticated;
grant select on public.tool_events,public.security_alerts to authenticated;

alter function public.validate_progress_report(jsonb) rename to validate_progress_report_v1;
revoke all on function public.validate_progress_report_v1(jsonb) from public,anon,authenticated;
create function public.validate_progress_report(p jsonb) returns void language plpgsql immutable set search_path=public as $$
declare e jsonb;
begin
  perform public.validate_progress_report_v1(p);
  if p ? 'learning_evidence' then
    if jsonb_typeof(p->'learning_evidence') <> 'array' or jsonb_array_length(p->'learning_evidence') > 12 then
      raise exception 'invalid learning evidence' using errcode='22023';
    end if;
    for e in select value from jsonb_array_elements(p->'learning_evidence') loop
      if jsonb_typeof(e) <> 'object' or not e ?& array['competency_id','state','actor','evidence_type','evidence','next_action']
        or coalesce(e->>'competency_id','') not in ('prompt_engineering','context_engineering','harness','skill_authoring','plugin_authoring','frontend','backend','databases','testing','devops','security')
        or coalesce(e->>'state','') not in ('unknown','practiced','demonstrated','needs_practice')
        or coalesce(e->>'actor','') not in ('learner','agent','together','unknown')
        or coalesce(e->>'evidence_type','') not in ('learner_action','learner_explanation','artifact_check','mentor_observation')
        or jsonb_typeof(e->'evidence') <> 'string' or jsonb_typeof(e->'next_action') <> 'string'
        or length(e->>'evidence') > 2000 or length(e->>'next_action') > 2000
        or (e->>'state' <> 'unknown' and btrim(e->>'evidence')='')
        or (e->>'state'='demonstrated' and e->>'actor'<>'learner') then
        raise exception 'learning evidence must describe observed learner actions' using errcode='22023';
      end if;
    end loop;
  end if;
  if p ? 'tool_usage' then
    if jsonb_typeof(p->'tool_usage') <> 'array' or jsonb_array_length(p->'tool_usage') > 12 then
      raise exception 'invalid tool usage' using errcode='22023';
    end if;
    for e in select value from jsonb_array_elements(p->'tool_usage') loop
      if jsonb_typeof(e) <> 'object' or not e ?& array['kind','tool_id','action','actor','evidence']
        or coalesce(e->>'kind','') not in ('skill','plugin','mcp','harness','tool')
        or coalesce(e->>'action','') not in ('used','created','configured')
        or coalesce(e->>'actor','') not in ('learner','agent','together','unknown')
        or jsonb_typeof(e->'tool_id') <> 'string' or length(e->>'tool_id') not between 1 and 160
        or jsonb_typeof(e->'evidence') <> 'string' or length(e->>'evidence') not between 1 and 2000 then
        raise exception 'invalid tool observation' using errcode='22023';
      end if;
    end loop;
  end if;
end;
$$;
revoke all on function public.validate_progress_report(jsonb) from public;

-- Keep the existing ingestion behavior, credentials, retry IDs and latest ordering.
alter function public.ingest(uuid,text,jsonb,jsonb,jsonb) rename to ingest_v5;
revoke all on function public.ingest_v5(uuid,text,jsonb,jsonb,jsonb) from public,anon,authenticated;
create function public.ingest(p_device uuid,p_secret text,p_identity jsonb default '{}'::jsonb,
  p_prompts jsonb default '[]'::jsonb,p_summary jsonb default null) returns jsonb
language plpgsql security definer set search_path=public as $$
declare result jsonb; sid uuid; before_prompt bigint; before_summary bigint; e jsonb; o jsonb; s jsonb; t jsonb; env jsonb; new_tool_id bigint;
begin
  perform pg_advisory_xact_lock(hashtextextended(coalesce(p_device::text,''),6));
  select id into sid from public.students where device_id=p_device;
  select coalesce(max(id),0) into before_prompt from public.prompts where student_id=sid;
  select coalesce(max(id),0) into before_summary from public.summaries where student_id=sid;
  result := public.ingest_v5(p_device,p_secret,p_identity,p_prompts,p_summary);
  select id into sid from public.students where device_id=p_device;
  for e in select value from jsonb_array_elements(coalesce(p_prompts,'[]'::jsonb)) loop
    o := nullif(e->'observability','null'::jsonb);
    if o is null then continue; end if;
    if jsonb_typeof(o)<>'object' or nullif(e->>'event_id','') is null or not o ?& array['version','tags','privacy_signals','tag_source'] or o->>'version'<>'1' or octet_length(o::text)>30000
      or o->>'tag_source'<>'keyword_rules' or o-array['version','tags','privacy_signals','tag_source','environment']<>'{}'::jsonb
      or jsonb_typeof(o->'tags')<>'array' or jsonb_array_length(o->'tags')>20
      or jsonb_typeof(o->'privacy_signals')<>'array' or jsonb_array_length(o->'privacy_signals')>12 then
      raise exception 'invalid prompt observation' using errcode='22023';
    end if;
    if exists(select from jsonb_array_elements_text(o->'tags') tag where tag not in
      ('frontend','backend','databases','testing','devops','prompt_engineering','context_engineering','harness','skill_authoring','plugin_authoring','security','intent:debug','intent:learn','intent:plan','intent:build','intent:review')) then
      raise exception 'invalid prompt tag' using errcode='22023';
    end if;
    for s in select value from jsonb_array_elements(o->'privacy_signals') loop
      if jsonb_typeof(s)<>'object' or not s ?& array['category','severity','count'] or coalesce(s->>'category','') not in ('api_key','private_key','credential','personal_contact','financial_id','confidential_marker')
        or coalesce(s->>'severity','') not in ('info','warning','critical') or jsonb_typeof(s->'count')<>'number'
        or (s->>'count')::numeric not between 1 and 100 or (s->>'count')::numeric<>trunc((s->>'count')::numeric)
        or (select count(*) from jsonb_object_keys(s))<>3 then
        raise exception 'invalid privacy signal' using errcode='22023';
      end if;
    end loop;
    update public.prompts set observability=o-'environment'
      where student_id=sid and event_id=nullif(e->>'event_id','')::uuid and id>before_prompt;
    insert into public.security_alerts(student_id,prompt_id,category,severity,occurrences,created_at)
      select sid,p.id,signals.value->>'category',signals.value->>'severity',(signals.value->>'count')::integer,p.created_at
      from public.prompts p cross join jsonb_array_elements(o->'privacy_signals') signals(value)
      where p.student_id=sid and p.event_id=nullif(e->>'event_id','')::uuid and p.id>before_prompt
        and signals.value->>'severity' in ('warning','critical') and signals.value->>'category'<>'personal_contact'
      on conflict(prompt_id,category) do nothing;
  end loop;
  env := nullif(p_identity->'environment','null'::jsonb);
  if env is not null then
    if jsonb_typeof(env)<>'object' or not env ?& array['version','client','tools','harness','truncated','coverage'] or env->>'version'<>'1' or octet_length(env::text)>25000
      or env-array['version','client','tools','harness','truncated','coverage']<>'{}'::jsonb
      or jsonb_typeof(env->'truncated')<>'boolean' or env->>'coverage' not in ('selected_app_and_project','project_only','not_available')
      or jsonb_typeof(env->'tools')<>'array' or jsonb_array_length(env->'tools')>64
      or jsonb_typeof(env->'harness')<>'array' or jsonb_array_length(env->'harness')>10 then
      raise exception 'invalid environment' using errcode='22023';
    end if;
    for t in select value from jsonb_array_elements(env->'tools') loop
      if jsonb_typeof(t)<>'object' or coalesce(t->>'kind','') not in ('skill','plugin','mcp','harness','tool')
        or jsonb_typeof(t->'tool_id')<>'string' or length(t->>'tool_id') not between 1 and 160
        or coalesce(t->>'scope','') not in ('user','project') or (select count(*) from jsonb_object_keys(t))<>3 then
        raise exception 'invalid environment tool' using errcode='22023';
      end if;
    end loop;
    if exists(select from jsonb_array_elements_text(env->'harness') flag where flag not in
      ('project_instructions','version_control','ci_configuration','test_configuration','app_hooks')) then
      raise exception 'invalid harness flag' using errcode='22023';
    end if;
    update public.students set environment=env,environment_updated_at=now() where id=sid;
  end if;
  t := nullif(p_identity->'tool_event','null'::jsonb);
  if t is not null then
    if jsonb_typeof(t)<>'object' or octet_length(t::text)>4000 or coalesce(t->>'kind','') not in ('skill','plugin','mcp','harness','tool')
      or coalesce(t->>'action','')<>'used' or coalesce(t->>'actor','')<>'agent' or coalesce(t->>'source','')<>'tool_hook'
      or jsonb_typeof(t->'tool_id')<>'string' or length(t->>'tool_id') not between 1 and 160
      or nullif(t->>'event_id','') is null or t - array['event_id','ts','client','kind','tool_id','action','actor','source','session_id','project','privacy_signals'] <> '{}'::jsonb then
      raise exception 'invalid tool event' using errcode='22023';
    end if;
    insert into public.tool_events(student_id,event_id,session_id,project,client,kind,tool_id,action,actor,source,created_at)
      values(sid,(t->>'event_id')::uuid,left(t->>'session_id',100),left(t->>'project',200),coalesce(t->>'client','unknown'),
        t->>'kind',t->>'tool_id','used','agent','tool_hook',coalesce(least((t->>'ts')::timestamptz,now()),now()))
      on conflict(student_id,event_id) do nothing returning id into new_tool_id;
    if t ? 'privacy_signals' then
      if jsonb_typeof(t->'privacy_signals')<>'array' or jsonb_array_length(t->'privacy_signals')>12 then
        raise exception 'invalid tool privacy signal' using errcode='22023';
      end if;
      for s in select value from jsonb_array_elements(t->'privacy_signals') loop
        if jsonb_typeof(s)<>'object' or not s ?& array['category','severity','count']
          or coalesce(s->>'category','') not in ('api_key','private_key','credential','personal_contact','financial_id','confidential_marker')
          or coalesce(s->>'severity','') not in ('info','warning','critical') or jsonb_typeof(s->'count')<>'number'
          or (s->>'count')::numeric not between 1 and 100 or (s->>'count')::numeric<>trunc((s->>'count')::numeric)
          or (select count(*) from jsonb_object_keys(s))<>3 then
          raise exception 'invalid tool privacy signal' using errcode='22023';
        end if;
        if new_tool_id is not null and s->>'severity' in ('warning','critical') and s->>'category'<>'personal_contact' then
          insert into public.security_alerts(student_id,tool_event_id,category,severity,occurrences)
            values(sid,new_tool_id,s->>'category',s->>'severity',(s->>'count')::integer) on conflict(tool_event_id,category) do nothing;
        end if;
      end loop;
    end if;
  end if;
  insert into public.tool_events(student_id,summary_id,session_id,project,client,kind,tool_id,action,actor,source,evidence,created_at)
    select sid,r.id,r.session_id,r.project,r.client,usage.value->>'kind',usage.value->>'tool_id',usage.value->>'action',usage.value->>'actor','mentor_report',usage.value->>'evidence',r.created_at
    from public.summaries r cross join jsonb_array_elements(coalesce(r.progress_report->'tool_usage','[]'::jsonb)) usage(value)
    where r.student_id=sid and r.id>before_summary on conflict(summary_id,kind,tool_id,action) do nothing;
  return result;
end;
$$;
revoke all on function public.ingest(uuid,text,jsonb,jsonb,jsonb) from public;
grant execute on function public.ingest(uuid,text,jsonb,jsonb,jsonb) to anon,authenticated;

create function public.competency_for_name(n text) returns text language sql immutable as $$
  select case
    when n ~* '(prompt|промпт|промт)' then 'prompt_engineering'
    when n ~* '(context|контекст|rag)' then 'context_engineering'
    when n ~* '(harness|харнес|оркестр|hooks|хуки)' then 'harness'
    when n ~* '(skill|скил)' then 'skill_authoring'
    when n ~* '(plugin|плагин)' then 'plugin_authoring'
    when n ~* '(react|frontend|фронтенд|css|html|верстк|интерфейс)' then 'frontend'
    when n ~* '(backend|бэкенд|бекенд|api|сервер)' then 'backend'
    when n ~* '(sql|баз.*данных|database|postgres)' then 'databases'
    when n ~* '(test|тест|провер)' then 'testing'
    when n ~* '(devops|deploy|депло|docker|ci/cd)' then 'devops'
    when n ~* '(security|безопасност|секрет|конфиденц)' then 'security'
    else null end;
$$;

create function public.student_observability(p_student uuid,p_days integer default 30) returns jsonb
language plpgsql stable security invoker set search_path=public as $$
declare start_at timestamptz; result jsonb;
begin
  if not public.is_admin() then raise exception 'Administrator access required' using errcode='42501'; end if;
  if p_days not in (14,30,90) then raise exception 'Period must be 14, 30 or 90 days' using errcode='22023'; end if;
  if not exists(select from public.students where id=p_student) then raise exception 'Student not found' using errcode='22023'; end if;
  start_at := ((now() at time zone 'UTC')::date-(p_days-1))::timestamp at time zone 'UTC';
  with reports as (select * from public.summaries where student_id=p_student and created_at>=start_at),
  observations as (
    select r.id as summary_id,r.created_at,r.project,r.session_id,r.progress_report->>'task' as task,
      r.progress_report->>'goal' as goal,r.progress_report->>'confidence' as confidence,
      e->>'competency_id' as competency_id,e->>'state' as state,e->>'actor' as actor,
      e->>'evidence_type' as evidence_type,e->>'evidence' as evidence,e->>'next_action' as next_action,
      'structured_report'::text as source
    from reports r cross join jsonb_array_elements(coalesce(r.progress_report->'learning_evidence','[]'::jsonb)) e
    union all
    select r.id,r.created_at,r.project,r.session_id,r.progress_report->>'task',r.progress_report->>'goal',r.progress_report->>'confidence',
      public.competency_for_name(e->>'name'),case e->>'status' when 'strength' then 'practiced' when 'needs_support' then 'needs_practice' when 'developing' then 'practiced' else 'unknown' end,
      'unknown','mentor_observation',e->>'evidence',e->>'next_action','legacy_report'
    from reports r cross join jsonb_array_elements(coalesce(r.progress_report->'skills','[]'::jsonb)) e
    where not r.progress_report ? 'learning_evidence' and public.competency_for_name(e->>'name') is not null
  ), ranked as (select *,row_number() over(partition by competency_id order by created_at desc,summary_id desc) as position from observations),
  skill_stats as (
    select competency_id,count(*) as observations,count(distinct summary_id) as tasks,
      count(distinct lower(btrim(coalesce(nullif(goal,''),task,'') || '|' || coalesce(project,'')))) filter(where state='demonstrated' and actor='learner' and evidence_type in ('learner_action','learner_explanation') and confidence in ('medium','high')) as independent_tasks,
      max(created_at) as last_observed
    from observations where state<>'unknown' group by competency_id
  ) select jsonb_build_object(
    'days',p_days,'period_start',start_at,'generated_at',now(),
    'metrics',jsonb_build_object(
      'prompts',(select count(*) from public.prompts where student_id=p_student and created_at>=start_at),
      'tagged_prompts',(select count(*) from public.prompts where student_id=p_student and created_at>=start_at and observability is not null),
      'summaries',(select count(*) from reports),'completed_tasks',(select count(distinct coalesce(nullif(progress_report->>'goal',''),progress_report->>'task') || '|' || coalesce(project,'')) from reports where progress_report->>'status'='completed'),
      'active_days',(select count(distinct (created_at at time zone 'UTC')::date) from public.prompts where student_id=p_student and created_at>=start_at),
      'projects',(select count(distinct project) from public.prompts where student_id=p_student and created_at>=start_at),
      'open_alerts',(select count(*) from public.security_alerts where student_id=p_student and status='open')),
    'skills',coalesce((select jsonb_agg(to_jsonb(s) || jsonb_build_object('latest_state',r.state,'next_action',r.next_action) order by s.competency_id)
      from skill_stats s join ranked r on r.competency_id=s.competency_id and r.position=1),'[]'::jsonb),
    'evidence',coalesce((select jsonb_agg(to_jsonb(e) order by e.created_at desc,e.summary_id desc)
      from (select * from ranked where position<=8 order by created_at desc,summary_id desc limit 88) e),'[]'::jsonb),
    'tags',coalesce((select jsonb_agg(jsonb_build_object('tag',tag,'count',n) order by n desc,tag) from (
      select tag,count(*) n from public.prompts p cross join lateral jsonb_array_elements_text(coalesce(p.observability->'tags','[]'::jsonb)) tag
      where student_id=p_student and created_at>=start_at group by tag) t),'[]'::jsonb),
    'directions',coalesce((select jsonb_agg(jsonb_build_object('direction',direction,'count',n) order by n desc) from (
      select direction,count(*) n from reports cross join lateral jsonb_array_elements_text(coalesce(progress_report->'directions','[]'::jsonb)) direction group by direction) d),'[]'::jsonb),
    'clients',coalesce((select jsonb_agg(jsonb_build_object('client',client,'count',n) order by n desc) from (
      select client,count(*) n from public.prompts where student_id=p_student and created_at>=start_at group by client) c),'[]'::jsonb),
    'tools',coalesce((select jsonb_agg(to_jsonb(t) order by t.last_used desc) from (
      select kind,tool_id,source,actor,action,count(*) as count,max(created_at) as last_used
      from public.tool_events where student_id=p_student and created_at>=start_at group by kind,tool_id,source,actor,action order by max(created_at) desc limit 100) t),'[]'::jsonb),
    'tool_events',coalesce((select jsonb_agg(to_jsonb(t) order by t.created_at desc,t.id desc) from (
      select * from public.tool_events where student_id=p_student and created_at>=start_at order by created_at desc,id desc limit 50) t),'[]'::jsonb),
    'environment',(select environment from public.students where id=p_student),
    'environment_updated_at',(select environment_updated_at from public.students where id=p_student),
    'activity',(select jsonb_agg(jsonb_build_object('date',d,'prompts',n) order by d) from (
      select (created_at at time zone 'UTC')::date d,count(*) n from public.prompts where student_id=p_student and created_at>=start_at group by d) a),
    'evidence_limit_per_skill',8,'tool_list_limit',100,'tool_event_limit',50
  ) into result;
  return result;
end;
$$;
revoke all on function public.student_observability(uuid,integer) from public;
grant execute on function public.student_observability(uuid,integer) to authenticated;

create function public.security_alert_counts() returns jsonb language plpgsql stable security invoker set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'Administrator access required' using errcode='42501'; end if;
  return (select jsonb_build_object('open',count(*) filter(where status='open'),'critical',count(*) filter(where status='open' and severity='critical'),'latest_id',coalesce(max(id),0)) from public.security_alerts);
end;
$$;
create function public.review_security_alert(p_alert bigint,p_status text) returns void language plpgsql security definer set search_path=public as $$
begin
  if not public.is_admin() then raise exception 'Administrator access required' using errcode='42501'; end if;
  if p_status not in ('reviewed','false_positive') then raise exception 'Invalid review state' using errcode='22023'; end if;
  update public.security_alerts set status=p_status,reviewed_at=now(),reviewed_by=auth.uid() where id=p_alert;
  if not found then raise exception 'Alert not found' using errcode='22023'; end if;
end;
$$;
revoke all on function public.security_alert_counts() from public;
revoke all on function public.review_security_alert(bigint,text) from public;
grant execute on function public.security_alert_counts(),public.review_security_alert(bigint,text) to authenticated;
